"""Capa Omni → Odoo para lo capturado por los bots: traduce clientes, productos, vendedor, moneda y diario
a ids de Odoo y crea el pedido de venta / pago **en borrador** (se confirman dentro de Odoo).

Reglas:
- Idempotente: antes de crear busca por la referencia del bot, así un reintento no duplica en Odoo.
- Datos que faltan en Odoo (producto, cliente de un pago, diario) no son errores técnicos: la ingesta queda
  como está con un motivo legible en ``error`` y se puede reintentar (``POST …/sincronizar/``).
- Los detalles técnicos (faults de Odoo) solo van al log, nunca a la API (R-CODE-8).

Configuración opcional en ``ConectorInstancia.configuracion`` (Odoo):
``diarios_pago``: {"default": 12, "transferencia": 12, "efectivo_usd": 5, …} (id de ``account.journal``);
``empujar_bots``: false para desactivar el envío automático.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from django.db import transaction

from apps.crm.models import Cliente
from apps.integration_hub.connectors.base import (
    ConnectorConnectionError,
    ConnectorError,
)
from apps.integration_hub.connectors.odoo.client import OdooCallError
from apps.integration_hub.connectors.odoo.connector import OdooConnector
from apps.integration_hub.models import ConectorInstancia, EntidadSincronizada
from apps.ventas.models import Pedido

from ..models import IngestaBot

logger = logging.getLogger(__name__)

KINDS_SINCRONIZABLES = (
    IngestaBot.Kind.PEDIDO,
    IngestaBot.Kind.PAGO,
    IngestaBot.Kind.PAGO_PROVEEDOR,
)
_ALIAS_MONEDA = {
    "BS": "VES",
    "BSF": "VES",
    "VEF": "VES",
    "VES": "VES",
    "USD": "USD",
    "$": "USD",
    "EUR": "EUR",
}


class NoSincronizable(Exception):
    """Falta algo en Odoo/Omni para empujar; mensaje legible para el equipo (no es un fallo técnico)."""


class ErrorTransitorio(Exception):
    """Fallo de conexión con Odoo: la tarea reintenta."""


def debe_sincronizar(ing: IngestaBot) -> bool:
    """Pedidos al crearse; pagos solo cuando están completos (BORRADOR)."""
    if ing.kind == IngestaBot.Kind.PEDIDO:
        return ing.estado == IngestaBot.Estado.PROCESADO
    if ing.kind in (IngestaBot.Kind.PAGO, IngestaBot.Kind.PAGO_PROVEEDOR):
        return ing.estado == IngestaBot.Estado.BORRADOR
    return False


def instancia_odoo(empresa) -> ConectorInstancia | None:
    return (
        ConectorInstancia.objects.filter(
            id_empresa=empresa,
            id_proveedor__codigo="odoo",
            estado="activo",
            activo=True,
        )
        .order_by("-fecha_creacion")
        .first()
    )


# ── resolución de ids ────────────────────────────────────────────────────────


def _es_id(valor) -> bool:
    return bool(valor) and str(valor).isdigit()


def _variantes_rif(rif: str) -> list[str]:
    limpio = re.sub(r"[^0-9A-Za-z]", "", rif or "").upper()
    return sorted(
        {rif.strip(), rif.strip().upper(), limpio, f"{limpio[:1]}-{limpio[1:]}"} - {""}
    )


def _partner_por_rif(cli, rif: str) -> int | None:
    if not rif or rif.upper().startswith("PEND-"):
        return None
    ids = cli.call(
        "res.partner", "search", [[["vat", "in", _variantes_rif(rif)]]], {"limit": 3}
    )
    if len(ids) > 1:
        raise NoSincronizable(
            f"El RIF {rif} está en {len(ids)} contactos de Odoo: vincúlalo manualmente."
        )
    return ids[0] if ids else None


def _datos_contacto(cliente: Cliente) -> dict:
    """Ficha del cliente para crear el contacto en Odoo, con el GPS de su entrega/fiscal o de su contacto."""
    dirs = cliente.direcciones.filter(activo=True, latitud__isnull=False)
    fuente = dirs.filter(tipo_direccion="ENTREGA").first() or dirs.first()
    if (
        fuente is None
        and cliente.contacto is not None
        and cliente.contacto.latitud is not None
    ):
        fuente = cliente.contacto
    gps = (
        {"latitud": fuente.latitud, "longitud": fuente.longitud}
        if fuente is not None
        else {}
    )
    return {
        "nombre": cliente.razon_social,
        "email": cliente.email,
        "telefono": cliente.telefono,
        "identificador_fiscal": cliente.rif,
        "direccion": cliente.direccion,
        "es_cliente": True,
        **gps,
    }


def _partner_cliente(
    conn: OdooConnector, cli, cliente: Cliente, *, crear: bool
) -> int | None:
    if _es_id(cliente.referencia_externa):
        return int(cliente.referencia_externa)
    pid = _partner_por_rif(cli, cliente.rif)
    if pid is None and crear:
        pid = int(conn.push_contacto(_datos_contacto(cliente)))
    if pid is not None:
        cliente.referencia_externa = str(pid)
        cliente.save(update_fields=["referencia_externa", "fecha_actualizacion"])
    return pid


def _partner_proveedor(cli, ing: IngestaBot) -> int:
    from apps.proveedores.models import Proveedor

    prov_id = ing.resultado.get("proveedor_id")
    prov = (
        Proveedor.objects.filter(pk=prov_id, id_empresa=ing.id_empresa).first()
        if prov_id
        else None
    )
    if prov is not None and _es_id(getattr(prov, "referencia_externa", None)):
        return int(prov.referencia_externa)
    if prov is not None and getattr(prov, "rif", ""):
        pid = _partner_por_rif(cli, prov.rif)
        if pid:
            return pid
    nombre = (ing.payload.get("proveedor") or "").strip()
    if not nombre:
        raise NoSincronizable("El pago no indica proveedor.")
    ids = cli.call(
        "res.partner",
        "search",
        [[["name", "=ilike", nombre], ["supplier_rank", ">", 0]]],
        {"limit": 3},
    )
    if len(ids) != 1:
        raise NoSincronizable(
            f"Proveedor «{nombre}» "
            + ("no encontrado en Odoo." if not ids else "ambiguo en Odoo.")
            + " Vincúlalo manualmente."
        )
    return ids[0]


def _producto_odoo(cli, inst, producto) -> int | None:
    """``product.product`` de un ``inventario.Producto``: por mapa de sync, referencia o SKU (``default_code``)."""
    m = EntidadSincronizada.objects.filter(
        id_instancia=inst, tipo_entidad="productos", id_omni=str(producto.pk)
    ).first()
    tmpl = (m.id_externo if m else None) or producto.referencia_externa
    if _es_id(tmpl):
        variantes = cli.get_variantes_producto(int(tmpl))
        if variantes:
            return variantes[0]["id"]
    if producto.sku:
        ids = cli.call(
            "product.product",
            "search",
            [[["default_code", "=", producto.sku]]],
            {"limit": 2},
        )
        if len(ids) == 1:
            return ids[0]
    return None


def _vendedor_odoo(cli, email: str) -> int | None:
    if not email:
        return None
    ids = cli.call(
        "res.users", "search", [[["login", "=ilike", email.strip()]]], {"limit": 1}
    )
    return ids[0] if ids else None


def _moneda_odoo(cli, codigo: str) -> int | None:
    objetivo = _ALIAS_MONEDA.get(
        (codigo or "").strip().upper(), (codigo or "").strip().upper()
    )
    for m in cli.get_monedas():
        if _ALIAS_MONEDA.get(m["name"].upper(), m["name"].upper()) == objetivo:
            return m["id"]
    return None


def _diario_odoo(cli, cfg: dict, metodo: str, moneda: str) -> int:
    norm = re.sub(r"[^a-z0-9]+", "_", (metodo or "").lower()).strip("_")
    mon = (moneda or "").lower()
    mapa = {str(k).lower(): v for k, v in (cfg.get("diarios_pago") or {}).items()}
    for clave in (f"{norm}_{mon}", norm, mon, "default"):
        if clave and _es_id(mapa.get(clave)):
            return int(mapa[clave])
    # Sin configuración: solo si hay un único diario banco/caja compatible con la moneda.
    obj = _ALIAS_MONEDA.get((moneda or "").upper(), (moneda or "").upper())
    candidatos = []
    for j in cli.get_diarios(["bank", "cash"]):
        cur = j.get("currency_id")
        nombre_cur = cur[1] if isinstance(cur, list) and len(cur) > 1 else None
        if (
            nombre_cur is None
            or _ALIAS_MONEDA.get(nombre_cur.upper(), nombre_cur.upper()) == obj
        ):
            candidatos.append(j["id"])
    if len(candidatos) == 1:
        return candidatos[0]
    raise NoSincronizable(
        "No hay un diario de pago inequívoco para este método/moneda: configura «diarios_pago» en el conector Odoo."
    )


# ── pedido ───────────────────────────────────────────────────────────────────


def _push_pedido(ing: IngestaBot, conn: OdooConnector, cli, inst) -> tuple[str, str]:
    ped = (
        Pedido.objects.select_related("id_cliente", "id_vendedor")
        .prefetch_related("detalles__id_producto")
        .filter(pk=ing.resultado.get("pedido_id"), id_empresa=ing.id_empresa)
        .first()
    )
    if ped is None:
        raise NoSincronizable("El pedido de Omni ya no existe.")
    if _es_id(ped.referencia_externa):  # ya empujado en un intento anterior
        return "sale.order", ped.referencia_externa

    lineas = []
    for d in ped.detalles.all():
        pid = _producto_odoo(cli, inst, d.id_producto)
        if pid is None:
            raise NoSincronizable(
                f"El producto «{d.id_producto.nombre_producto}» no existe en Odoo."
            )
        lineas.append(
            {"product_id": pid, "cantidad": d.cantidad, "precio": d.precio_unitario}
        )
    partner = _partner_cliente(conn, cli, ped.id_cliente, crear=True)

    ref = ped.numero_pedido  # referencia del bot: sirve para no duplicar al reintentar
    previos = cli.call(
        "sale.order",
        "search",
        [[["client_order_ref", "=", ref], ["partner_id", "=", partner]]],
        {"limit": 1},
    )
    if previos:
        oid = previos[0]
    else:
        email = ped.id_vendedor.email if ped.id_vendedor_id else ""
        oid = int(
            conn.push_pedido_venta(
                {
                    "partner_id": partner,
                    "lineas": lineas,
                    "referencia": ref,
                    "nota": ped.observaciones,
                    "vendedor_id": _vendedor_odoo(cli, email),
                    "fecha_entrega": ped.fecha_cierre_estimada.isoformat() + " 12:00:00"
                    if ped.fecha_cierre_estimada
                    else None,
                }
            )
        )
    nombre = cli.call("sale.order", "read", [[oid]], {"fields": ["name"]})[0]["name"]
    with transaction.atomic():
        ped.referencia_externa = str(oid)
        ped.documento_json = {
            **(ped.documento_json or {}),
            "numero_bot": ref,
            "odoo_name": nombre,
        }
        # Con el nombre de Odoo (p. ej. S00553) la sync entrante lo reconoce y no duplica el pedido.
        if (
            not Pedido.objects.filter(id_empresa=ped.id_empresa, numero_pedido=nombre)
            .exclude(pk=ped.pk)
            .exists()
        ):
            ped.numero_pedido = nombre
        ped.save(
            update_fields=["referencia_externa", "documento_json", "numero_pedido"]
        )
    return "sale.order", str(oid)


# ── pagos ────────────────────────────────────────────────────────────────────


def _push_pago(ing: IngestaBot, conn: OdooConnector, cli, inst) -> tuple[str, str]:
    p, es_cliente = ing.payload, ing.kind == IngestaBot.Kind.PAGO
    if es_cliente:
        cliente = Cliente.objects.filter(
            pk=ing.resultado.get("cliente_id"), id_empresa=ing.id_empresa
        ).first()
        if cliente is None:
            raise NoSincronizable(
                "Cliente del pago no identificado en Omni: vincúlalo en Odoo."
            )
        partner = _partner_cliente(conn, cli, cliente, crear=False)
        if partner is None:
            raise NoSincronizable(
                f"El cliente «{cliente.razon_social}» no existe en Odoo: vincula el pago allí."
            )
    else:
        partner = _partner_proveedor(cli, ing)

    monto = Decimal(str(p["monto"]))
    moneda_id = _moneda_odoo(cli, p.get("moneda", ""))
    if moneda_id is None:
        raise NoSincronizable(f"Moneda «{p.get('moneda')}» no encontrada en Odoo.")
    diario = _diario_odoo(
        cli, inst.get_config(), p.get("metodo_pago", ""), p.get("moneda", "")
    )

    marca = f"BOT-{str(ing.pk)[-8:]}"
    partes = [
        marca,
        f"ref {p.get('referencia')}" if p.get("referencia") else "",
        p.get("banco") or "",
        p.get("metodo_pago") or "",
        f"pedido {p['pedido_ref']}" if p.get("pedido_ref") else "",
        f"factura {p['factura_ref']}" if p.get("factura_ref") else "",
    ]
    memo = " · ".join(x for x in partes if x)
    try:  # idempotencia: si un reintento ya creó el pago, se reutiliza
        previos = cli.call(
            "account.payment", "search", [[["memo", "ilike", marca]]], {"limit": 1}
        )
    except OdooCallError:
        previos = []
    if previos:
        return "account.payment", str(previos[0])
    oid = conn.push_pago(
        {
            "partner_id": partner,
            "monto": monto,
            "journal_id": diario,
            "moneda_id": moneda_id,
            "tipo": "cliente" if es_cliente else "proveedor",
            "fecha": p.get("fecha_pago"),
            "referencia": memo,
        }
    )
    return "account.payment", str(oid)


_PUSHERS = {
    IngestaBot.Kind.PEDIDO: _push_pedido,
    IngestaBot.Kind.PAGO: _push_pago,
    IngestaBot.Kind.PAGO_PROVEEDOR: _push_pago,
}


# ── orquestación ─────────────────────────────────────────────────────────────


def _anotar(ing: IngestaBot, error: str) -> None:
    ing.error = error[:255]
    ing.save(update_fields=["error", "fecha_actualizacion"])


def sincronizar(ing: IngestaBot) -> IngestaBot:
    """Empuja la ingesta a Odoo. Lanza ``ErrorTransitorio`` solo si conviene reintentar."""
    if (
        ing.estado == IngestaBot.Estado.SINCRONIZADO
        or ing.kind not in KINDS_SINCRONIZABLES
    ):
        return ing
    inst = instancia_odoo(ing.id_empresa)
    if inst is None or inst.get_config().get("empujar_bots") is False:
        return ing  # sin Odoo conectado (o desactivado): no hay nada que empujar
    if not debe_sincronizar(ing):
        _anotar(ing, "Faltan datos: complétala antes de enviarla a Odoo.")
        return ing
    conn = OdooConnector(inst)
    try:
        cli = conn._get_client()
        modelo, oid = _PUSHERS[ing.kind](ing, conn, cli, inst)
    except NoSincronizable as e:
        _anotar(ing, str(e))
        return ing
    except ConnectorConnectionError as e:
        logger.warning("Odoo no disponible al sincronizar ingesta %s", ing.pk)
        raise ErrorTransitorio("Odoo no disponible") from e
    except (ConnectorError, OdooCallError):
        logger.exception("Falló el envío a Odoo de la ingesta %s", ing.pk)
        _anotar(ing, "Odoo rechazó el envío; revisa los datos o reintenta.")
        return ing
    ing.estado = IngestaBot.Estado.SINCRONIZADO
    ing.odoo_ref = f"{modelo}:{oid}"
    ing.error = ""
    ing.resultado = {**ing.resultado, "odoo": {"modelo": modelo, "id": oid}}
    ing.save(
        update_fields=[
            "estado",
            "odoo_ref",
            "error",
            "resultado",
            "fecha_actualizacion",
        ]
    )
    return ing
