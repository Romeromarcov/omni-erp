"""Capa Omni → Odoo para lo capturado por los bots: traduce clientes, proveedores, productos,
vendedor, moneda y diario a ids de Odoo y crea borradores auditables (nunca confirma ni publica).

Tipos sincronizables (paridad 100 % con CxC producción):
- ``contacto``          → ``res.partner`` borrador (``customer_rank=0``, nota ``[Borrador Telegram]``)
- ``pedido``            → ``sale.order`` en borrador (+ alta de ``res.partner`` cliente si no existe)
- ``pago``              → ``account.payment`` inbound en borrador
- ``pago_proveedor``    → ``account.payment`` outbound en borrador (+ referencia opcional a ``account.move``)
- ``proveedor``         → ``res.partner`` proveedor en borrador (``supplier_rank=1``, serializado por RIF)
- ``factura_proveedor`` → ``account.move`` ``in_invoice`` en borrador (sin impuestos inventados; IVA en nota)
- ``gasto``             → ``account.move`` ``in_invoice`` en borrador al contado (sin vencimiento; categoría en nota)

Reglas:
- **Interruptor estricto**: requiere ``empujar_bots: true`` en ``ConectorInstancia.configuracion``.
  Por defecto NO escribe en Odoo para convivir en paralelo con CxC producción sin duplicar.
- **Credencial de mínimo privilegio opcional**: si ``write_user`` y ``write_api_key`` están definidos
  en ``ConectorInstancia.configuracion``, toda escritura usa esa cuenta dedicada sin tocar la de lectura.
- **Idempotente**: cada creación lleva marca ``BOT-<uuid>`` y se busca antes de crear, evitando duplicados.
- **Sin filtrar detalles técnicos (R-CODE-8)**: faults XML-RPC solo van al log; en ``IngestaBot.error``
  queda únicamente un mensaje funcional legible.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
import logging
import re
from typing import Any
import unicodedata
import xmlrpc.client  # nosec B411 - solo se referencia ProtocolError para clasificar errores de red

from django.db import connection, transaction

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

NOTA_BORRADOR = "[Borrador Telegram] pendiente de completar"
NOTA_PROVEEDOR_DE_DOCUMENTO = (
    "[Borrador Telegram] proveedor creado desde un documento; revisar"
)

KINDS_SINCRONIZABLES = (
    IngestaBot.Kind.CONTACTO,
    IngestaBot.Kind.PEDIDO,
    IngestaBot.Kind.PAGO,
    IngestaBot.Kind.PAGO_PROVEEDOR,
    IngestaBot.Kind.PROVEEDOR,
    IngestaBot.Kind.FACTURA_PROVEEDOR,
    IngestaBot.Kind.GASTO,
)

_KINDS_PROCESADO = (
    IngestaBot.Kind.CONTACTO,
    IngestaBot.Kind.PEDIDO,
    IngestaBot.Kind.PROVEEDOR,
    IngestaBot.Kind.FACTURA_PROVEEDOR,
    IngestaBot.Kind.GASTO,
)

_RIF_RX = re.compile(r"^\s*([VJEGBPvjegbp])[-\s]?([0-9][0-9\-\s]*)\s*$")


class NoSincronizable(Exception):
    """Falta algo en Odoo/Omni para empujar; mensaje legible para el equipo (no es un fallo técnico)."""


class ErrorTransitorio(Exception):
    """Fallo de conexión o bloqueo en curso: la tarea Celery reintenta con backoff."""


class _InstanciaEscritura:
    """Proyecta ``write_user`` / ``write_api_key`` como credencial activa sin mutar ``ConectorInstancia``."""

    def __init__(self, instancia: Any) -> None:
        self._instancia = instancia

    def get_config(self) -> dict[str, Any]:
        cfg = dict(self._instancia.get_config() or {})
        write_user = str(cfg.get("write_user") or "").strip()
        write_key = str(cfg.get("write_api_key") or "").strip()
        if write_user and write_key:
            cfg["user"] = write_user
            cfg["api_key"] = write_key
        elif write_user or write_key:
            raise NoSincronizable(
                "Configura tanto «write_user» como «write_api_key» en el conector Odoo."
            )
        return cfg


def debe_sincronizar(ing: IngestaBot) -> bool:
    """Contactos/pedidos/proveedores/facturas/gastos completos (PROCESADO); pagos en BORRADOR."""
    if ing.kind in _KINDS_PROCESADO:
        return ing.estado == IngestaBot.Estado.PROCESADO
    if ing.kind in (IngestaBot.Kind.PAGO, IngestaBot.Kind.PAGO_PROVEEDOR):
        return ing.estado == IngestaBot.Estado.BORRADOR
    return False


def instancia_odoo(empresa) -> ConectorInstancia | None:
    """Conector Odoo activo de la empresa activa: la MISMA selección que usa CxC Lubrikca."""
    return (
        ConectorInstancia.objects.select_related("id_proveedor", "id_empresa")
        .filter(
            id_empresa=empresa,
            id_empresa__activo=True,
            id_proveedor__codigo="odoo",
            activo=True,
        )
        .order_by("-fecha_actualizacion")
        .first()
    )


# ── utilidades y resolución de ids ───────────────────────────────────────────


def _vacio(v: Any) -> bool:
    return v in (None, "", [], {})


def _es_id(valor: Any) -> bool:
    return bool(valor) and str(valor).isdigit()


def _marca(ing: IngestaBot) -> str:
    return f"BOT-{ing.pk}"


def _decimal_seguro(valor: Any, campo: str) -> Decimal:
    try:
        d = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise NoSincronizable(f"Monto inválido en «{campo}».") from exc
    if not d.is_finite():
        raise NoSincronizable(f"Monto inválido en «{campo}».")
    return d


def _canon_rif(rif: Any) -> str | None:
    """Normaliza ``j 29888777-1`` / ``J298887771`` → ``J-298887771``; ignora vacíos y ``PEND-…``."""
    raw = str(rif or "").strip()
    if not raw or raw.upper().startswith("PEND-"):
        return None
    m = _RIF_RX.match(raw)
    if m:
        return f"{m.group(1).upper()}-{re.sub(r'[^0-9]', '', m.group(2))}"
    limpio = re.sub(r"[^0-9A-Za-z]", "", raw).upper()
    return f"{limpio[:1]}-{limpio[1:]}" if len(limpio) >= 2 else None


def _variantes_rif(rif: str) -> list[str]:
    """Todas las grafías habituales de RIF en Odoo/l10n_ve (con y sin guion de dígito verificador)."""
    canon = _canon_rif(rif)
    if not canon:
        return []
    letra, digs = canon[0], canon[2:]
    variantes = {
        rif.strip(),
        rif.strip().upper(),
        canon,
        f"{letra}{digs}",
        digs,
    }
    if len(digs) >= 2:
        variantes.add(f"{letra}-{digs[:-1]}-{digs[-1]}")
    return sorted(variantes - {""})


def _sin_acentos(texto: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", (texto or "").lower())
        if unicodedata.category(c) != "Mn"
    )


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _sin_acentos(texto)).strip("_")


def _ilike_exacto(texto: str) -> str:
    """Escapa comodines SQL para que ``=ilike`` actúe como igualdad insensible a mayúsculas."""
    return (
        (texto or "")
        .strip()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _vals(**kw: Any) -> dict[str, Any]:
    """Filtra ``None`` para llamadas XML-RPC."""
    return {k: v for k, v in kw.items() if v is not None}


def _fecha_iso(valor: Any) -> str | None:
    if _vacio(valor):
        return None
    try:
        return date.fromisoformat(str(valor)[:10]).isoformat()
    except ValueError:
        return None


def _id_creado(res: Any) -> int:
    return int(res[0] if isinstance(res, list) else res)


@contextmanager
def _bloqueo_partner_tx(empresa_id: Any, clave: str):
    """Serializa por ``(empresa, socio)`` en PostgreSQL para evitar duplicar ``res.partner``."""
    llave = f"bots_odoo_partner:{empresa_id}:{clave}"
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s))", [llave])
            fila = cur.fetchone()
        if not fila or not fila[0]:
            raise ErrorTransitorio(
                "Hay otro envío del mismo contacto/proveedor en curso; se reintentará."
            )
        yield


def _partner_por_rif(cli, rif: str | None) -> int | None:
    variantes = _variantes_rif(rif or "")
    if not variantes:
        return None
    ids = cli.call(
        "res.partner", "search", [[["vat", "in", variantes]]], {"limit": 3}
    )
    if len(ids) > 1:
        raise NoSincronizable(
            f"El RIF {rif} está en {len(ids)} contactos de Odoo: vincúlalo manualmente."
        )
    return int(ids[0]) if ids else None


def _partner_por_marca(cli, marca: str) -> int | None:
    ids = cli.call("res.partner", "search", [[["ref", "=", marca]]], {"limit": 1})
    return int(ids[0]) if ids else None


def _buscar_partner_exacto(
    cli, nombre: str, *, solo_proveedores: bool = False
) -> list[int]:
    dom: list[Any] = [["name", "=ilike", _ilike_exacto(nombre)]]
    if solo_proveedores:
        dom.append(["supplier_rank", ">", 0])
    ids = cli.call("res.partner", "search", [dom], {"limit": 3})
    return [int(i) for i in ids]


def _campos_modelo_opcional(cli, modelo: str) -> set[str] | None:
    """Devuelve el conjunto de campos vía ``fields_get`` o ``None`` si el doble de test no lo define."""
    try:
        info = cli.call(modelo, "fields_get", [], {"attributes": ["string"]})
    except KeyError:
        return None
    return set(info or {})


def _crear_partner_borrador(
    cli, vals: dict[str, Any], *, lat: Any = None, lon: Any = None
) -> int:
    """Crea ``res.partner`` en borrador; si Odoo no tiene ``base_geolocalize`` reintenta sin GPS."""
    if lat is None or lon is None:
        return _id_creado(cli.call("res.partner", "create", [vals]))
    # Conversión intencional en la frontera XML-RPC hacia Odoo (Float externo).
    con_gps = {
        **vals,
        "partner_latitude": float(_decimal_seguro(lat, "latitud")),
        "partner_longitude": float(_decimal_seguro(lon, "longitud")),
    }
    try:
        return _id_creado(cli.call("res.partner", "create", [con_gps]))
    except OdooCallError as exc:
        if "partner_latitude" not in str(exc) and "partner_longitude" not in str(exc):
            raise
        logger.warning(
            "Odoo sin campos de geolocalización: se crea res.partner sin GPS"
        )
        return _id_creado(cli.call("res.partner", "create", [vals]))


def _datos_contacto(cliente: Cliente) -> dict[str, Any]:
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
        "identificador_fiscal": _canon_rif(cliente.rif) or cliente.rif,
        "direccion": cliente.direccion,
        "es_cliente": True,
        **gps,
    }


def _partner_cliente(
    conn: OdooConnector, cli, cliente: Cliente, *, crear: bool
) -> int | None:
    if _es_id(cliente.referencia_externa):
        return int(cliente.referencia_externa)
    if not crear:
        pid = _partner_por_rif(cli, cliente.rif)
        if pid is not None:
            cliente.referencia_externa = str(pid)
            cliente.save(update_fields=["referencia_externa", "fecha_actualizacion"])
        return pid

    canon = _canon_rif(cliente.rif)
    clave = f"cli_rif:{canon}" if canon else f"cli_id:{cliente.pk}"
    with _bloqueo_partner_tx(cliente.id_empresa_id, clave):
        cliente.refresh_from_db(fields=["referencia_externa"])
        if _es_id(cliente.referencia_externa):
            return int(cliente.referencia_externa)
        pid = _partner_por_rif(cli, cliente.rif)
        if pid is None:
            pid = int(conn.push_contacto(_datos_contacto(cliente)))
        cliente.referencia_externa = str(pid)
        cliente.save(update_fields=["referencia_externa", "fecha_actualizacion"])
        return pid


def _partner_cliente_pago(conn: OdooConnector, cli, ing: IngestaBot) -> int:
    """Resuelve el ``res.partner`` de un pago de cliente sin crear nunca socios nuevos."""
    p = ing.payload
    cliente = (
        Cliente.objects.filter(
            pk=ing.resultado.get("cliente_id"), id_empresa=ing.id_empresa
        ).first()
        if ing.resultado.get("cliente_id")
        else None
    )
    if cliente is not None:
        pid = _partner_cliente(conn, cli, cliente, crear=False)
        if pid is not None:
            return pid

    # Fallback solo lectura en Odoo (pedido_ref -> RIF -> nombre exacto), paridad con CxC
    if not _vacio(p.get("pedido_ref")):
        ordenes = cli.call(
            "sale.order",
            "search_read",
            [[["name", "=ilike", _ilike_exacto(str(p["pedido_ref"]))]]],
            {"fields": ["partner_id"], "limit": 2},
        )
        if (
            len(ordenes) == 1
            and isinstance(ordenes[0].get("partner_id"), (list, tuple))
            and ordenes[0]["partner_id"]
        ):
            return int(ordenes[0]["partner_id"][0])

    pid_rif = _partner_por_rif(cli, p.get("rif"))
    if pid_rif is not None:
        return pid_rif

    nombre = str(
        p.get("cliente") or (cliente.razon_social if cliente is not None else "")
    ).strip()
    if nombre:
        ids = _buscar_partner_exacto(cli, nombre, solo_proveedores=False)
        if len(ids) > 1:
            raise NoSincronizable(
                f"Hay varios clientes llamados «{nombre}» en Odoo: vincula el pago allí."
            )
        if len(ids) == 1:
            return ids[0]

    etiqueta = f"«{nombre}» " if nombre else ""
    raise NoSincronizable(
        f"El cliente {etiqueta}no existe en Odoo: vincula el pago allí."
    )


def _guardar_ref_proveedor(prov, pid: int) -> None:
    if prov is not None and prov.referencia_externa != str(pid):
        prov.referencia_externa = str(pid)
        prov.save(update_fields=["referencia_externa", "fecha_actualizacion"])


def _partner_proveedor_pago(cli, ing: IngestaBot) -> int:
    from apps.proveedores.models import Proveedor

    prov_id = ing.resultado.get("proveedor_id")
    prov = (
        Proveedor.objects.filter(pk=prov_id, id_empresa=ing.id_empresa).first()
        if prov_id
        else None
    )
    if prov is not None and _es_id(prov.referencia_externa):
        return int(prov.referencia_externa)
    rif = _canon_rif(ing.payload.get("rif")) or (
        _canon_rif(prov.rif) if prov is not None else None
    )
    if rif:
        pid = _partner_por_rif(cli, rif)
        if pid:
            _guardar_ref_proveedor(prov, pid)
            return pid
    nombre = str(
        ing.payload.get("proveedor") or (prov.razon_social if prov is not None else "")
    ).strip()
    if not nombre:
        raise NoSincronizable("El pago no indica proveedor.")
    ids = _buscar_partner_exacto(cli, nombre, solo_proveedores=True)
    if len(ids) != 1:
        raise NoSincronizable(
            f"Proveedor «{nombre}» "
            + ("no encontrado en Odoo." if not ids else "ambiguo en Odoo.")
            + " Vincúlalo manualmente."
        )
    pid = ids[0]
    _guardar_ref_proveedor(prov, pid)
    return pid


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
    """``res.users`` por ``login`` y, si no, por ``email``; si hay más de uno no se adivina."""
    if not email:
        return None
    e = _ilike_exacto(email)
    ids = cli.call(
        "res.users",
        "search",
        [["|", ["login", "=ilike", e], ["email", "=ilike", e]]],
        {"limit": 2},
    )
    return ids[0] if len(ids) == 1 else None


# Como en CxC: el dólar se llama exactamente "USD"; el bolívar aparece como VES/VEF/VED según la versión.
_FAMILIA_VES = {"VES", "VEF", "VED", "BS", "BSF", "BSD"}


def _clase_moneda(codigo: str) -> str:
    c = (codigo or "").strip().upper()
    return "USD" if c in ("USD", "$") else "VES" if c in _FAMILIA_VES else c


def _moneda_odoo(cli, codigo: str) -> int | None:
    c = (codigo or "").strip().upper()
    monedas = cli.get_monedas()
    if c in ("USD", "$"):
        return next((m["id"] for m in monedas if m["name"].upper() == "USD"), None)
    if c in _FAMILIA_VES:
        return next(
            (m["id"] for m in monedas if m["name"].upper() in _FAMILIA_VES), None
        )
    return next((m["id"] for m in monedas if m["name"].upper() == c), None)


def _diario_odoo(
    cli, cfg: dict[str, Any], metodo: str, moneda: str, banco: str = ""
) -> int:
    norm_banco = _slug(banco)
    norm_metodo = _slug(metodo)
    mon = _clase_moneda(moneda).lower()
    mapa = {_slug(str(k)): v for k, v in (cfg.get("diarios_pago") or {}).items()}
    claves = (
        f"{norm_banco}_{mon}" if norm_banco else "",
        norm_banco,
        f"{norm_metodo}_{mon}" if norm_metodo else "",
        norm_metodo,
        mon,
        "default",
    )
    for clave in claves:
        if clave and _es_id(mapa.get(clave)):
            return int(mapa[clave])
    # Sin configuración: solo si hay un único diario banco/caja compatible con la moneda.
    obj = _clase_moneda(moneda)
    candidatos = []
    for j in cli.get_diarios(["bank", "cash"]):
        cur = j.get("currency_id")
        nombre_cur = cur[1] if isinstance(cur, list) and len(cur) > 1 else None
        if nombre_cur is None or _clase_moneda(nombre_cur) == obj:
            candidatos.append(j["id"])
    if len(candidatos) == 1:
        return candidatos[0]
    raise NoSincronizable(
        "No hay un diario de pago inequívoco para este método/moneda: configura «diarios_pago» en el conector Odoo."
    )


# ── contacto (borrador CRM) ──────────────────────────────────────────────────


def _push_contacto(
    ing: IngestaBot, conn: OdooConnector, cli, inst
) -> tuple[str, str]:
    marca = _marca(ing)
    previo = _partner_por_marca(cli, marca)
    if previo is not None:
        return "res.partner", str(previo)
    p = ing.payload
    ub = p.get("ubicacion") or {}
    nota = NOTA_BORRADOR + (f"\n{p['notas']}" if not _vacio(p.get("notas")) else "")
    vals = _vals(
        name=str(p["nombre"]).strip(),
        phone=str(p["telefono"]).strip(),
        email=str(p["email"]).strip() if not _vacio(p.get("email")) else None,
        comment=nota,
        customer_rank=0,
        ref=marca,
    )
    pid = _crear_partner_borrador(
        cli, vals, lat=ub.get("latitud"), lon=ub.get("longitud")
    )
    return "res.partner", str(pid)


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
    if _es_id(ped.referencia_externa):
        return "sale.order", str(ped.referencia_externa)

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

    ref = ped.numero_pedido
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


# ── pagos (clientes y proveedores) ───────────────────────────────────────────


def _factura_proveedor_por_ref(cli, partner_id: int, numero: str) -> int | None:
    """Busca ``account.move`` ``in_invoice`` por ``(partner_id, ref)``. Estricto: propaga errores XML-RPC."""
    ids = cli.call(
        "account.move",
        "search",
        [
            [
                ["move_type", "=", "in_invoice"],
                ["partner_id", "=", partner_id],
                ["ref", "=", numero.strip()],
            ]
        ],
        {"limit": 1},
    )
    return int(ids[0]) if ids else None


def _campo_memo_pago(cli) -> str:
    campos = _campos_modelo_opcional(cli, "account.payment")
    if campos is None:
        return "memo"
    for c in ("memo", "payment_reference", "ref"):
        if c in campos:
            return c
    raise NoSincronizable(
        "No encuentro el campo de referencia en account.payment: revisa la versión de Odoo."
    )


def _push_pago(ing: IngestaBot, conn: OdooConnector, cli, inst) -> tuple[str, str]:
    p, es_cliente = ing.payload, ing.kind == IngestaBot.Kind.PAGO
    partner = (
        _partner_cliente_pago(conn, cli, ing)
        if es_cliente
        else _partner_proveedor_pago(cli, ing)
    )

    monto = _decimal_seguro(p.get("monto"), "monto")
    moneda_id = _moneda_odoo(cli, p.get("moneda", ""))
    if moneda_id is None:
        raise NoSincronizable(f"Moneda «{p.get('moneda')}» no encontrada en Odoo.")
    diario = _diario_odoo(
        cli,
        inst.get_config(),
        p.get("metodo_pago", ""),
        p.get("moneda", ""),
        p.get("banco", ""),
    )

    marca = _marca(ing)
    factura_txt = f"factura {p['factura_ref']}" if p.get("factura_ref") else ""
    if not es_cliente and factura_txt:
        fid = _factura_proveedor_por_ref(cli, partner, str(p["factura_ref"]))
        if fid is not None:
            factura_txt += f" [account.move {fid}]"
    partes = [
        marca,
        f"ref {p.get('referencia')}" if p.get("referencia") else "",
        p.get("banco") or "",
        p.get("metodo_pago") or "",
        f"pedido {p['pedido_ref']}" if p.get("pedido_ref") else "",
        factura_txt,
    ]
    memo = " · ".join(x for x in partes if x)
    campo_memo = _campo_memo_pago(cli)
    previos = cli.call(
        "account.payment", "search", [[[campo_memo, "ilike", marca]]], {"limit": 1}
    )
    if previos:
        return "account.payment", str(previos[0])

    fecha_pago = _fecha_iso(p.get("fecha_pago"))
    if campo_memo == "memo":
        oid = conn.push_pago(
            {
                "partner_id": partner,
                "monto": monto,
                "journal_id": diario,
                "moneda_id": moneda_id,
                "tipo": "cliente" if es_cliente else "proveedor",
                "fecha": fecha_pago,
                "referencia": memo,
            }
        )
        return "account.payment", str(oid)

    # Odoo < 18: ``account.payment`` usa ``payment_reference`` o ``ref`` en lugar de ``memo``.
    vals = _vals(
        partner_id=partner,
        amount=float(monto),
        payment_type="inbound" if es_cliente else "outbound",
        partner_type="customer" if es_cliente else "supplier",
        journal_id=diario,
        currency_id=moneda_id,
        date=fecha_pago,
        **{campo_memo: memo},
    )
    return "account.payment", str(_id_creado(cli.call("account.payment", "create", [vals])))


# ── proveedor y documentos de compra (factura_proveedor y gasto) ─────────────


def _crear_proveedor_odoo(cli, datos: dict[str, Any], marca: str) -> int:
    notas = [datos.get("nota_cabecera") or NOTA_BORRADOR]
    if not _vacio(datos.get("dias_credito")):
        notas.append(f"Días de crédito: {datos['dias_credito']}")
    if not _vacio(datos.get("notas")):
        notas.append(str(datos["notas"]))
    rif = _canon_rif(datos.get("rif"))
    vals = _vals(
        name=str(datos["nombre"]).strip(),
        vat=rif,
        phone=str(datos["telefono"]).strip()
        if not _vacio(datos.get("telefono"))
        else None,
        email=str(datos["email"]).strip() if not _vacio(datos.get("email")) else None,
        street=str(datos["direccion"]).strip()
        if not _vacio(datos.get("direccion"))
        else None,
        company_type=(
            ("company" if rif[0] in ("J", "G") else "person") if rif else None
        ),
        supplier_rank=1,
        customer_rank=0,
        comment="\n".join(notas),
        ref=marca,
    )
    return _crear_partner_borrador(
        cli, vals, lat=datos.get("lat"), lon=datos.get("lon")
    )


def _push_proveedor(
    ing: IngestaBot, conn: OdooConnector, cli, inst
) -> tuple[str, str]:
    from apps.proveedores.models import Proveedor

    p = ing.payload
    prov_id = ing.resultado.get("proveedor_id")
    prov = (
        Proveedor.objects.select_related("contacto")
        .filter(pk=prov_id, id_empresa=ing.id_empresa)
        .first()
        if prov_id
        else None
    )
    if prov is not None and _es_id(prov.referencia_externa):
        return "res.partner", str(prov.referencia_externa)

    rif = _canon_rif(p.get("rif")) or (_canon_rif(prov.rif) if prov else None)
    nombre = str(p.get("nombre") or (prov.razon_social if prov else "")).strip()
    if not nombre:
        raise NoSincronizable("El proveedor no tiene nombre para enviarlo a Odoo.")
    marca = _marca(ing)
    clave_lock = f"rif:{rif}" if rif else f"nom:{_slug(nombre)}"

    with _bloqueo_partner_tx(ing.id_empresa_id, clave_lock):
        if prov is not None:
            prov.refresh_from_db(fields=["referencia_externa"])
            if _es_id(prov.referencia_externa):
                return "res.partner", str(prov.referencia_externa)
        propio = _partner_por_marca(cli, marca)
        if propio is not None:
            _guardar_ref_proveedor(prov, propio)
            return "res.partner", str(propio)
        pid = _partner_por_rif(cli, rif)
        if pid is None:
            ids = _buscar_partner_exacto(cli, nombre, solo_proveedores=False)
            if len(ids) > 1:
                raise NoSincronizable(
                    f"Hay {len(ids)} contactos llamados «{nombre}» en Odoo: vincúlalo manualmente."
                )
            pid = ids[0] if ids else None
        if pid is not None:
            _guardar_ref_proveedor(prov, pid)
            return "res.partner", str(pid)

        ub = p.get("ubicacion") or {}
        lat = ub.get("latitud")
        lon = ub.get("longitud")
        if (lat is None or lon is None) and prov is not None and prov.contacto is not None:
            lat = prov.contacto.latitud
            lon = prov.contacto.longitud
        pid = _crear_proveedor_odoo(
            cli,
            {
                "nombre": nombre,
                "rif": rif,
                "telefono": p.get("telefono") or (prov.telefono if prov else None),
                "email": p.get("email") or (prov.email if prov else None),
                "direccion": p.get("direccion") or (prov.direccion if prov else None),
                "dias_credito": p.get("dias_credito"),
                "notas": p.get("notas"),
                "lat": lat,
                "lon": lon,
            },
            marca,
        )
        _guardar_ref_proveedor(prov, pid)
        return "res.partner", str(pid)


def _resolver_o_crear_proveedor_documento(
    ing: IngestaBot, cli, marca: str
) -> tuple[int, bool]:
    """Resuelve o crea el proveedor en Odoo para ``factura_proveedor`` o ``gasto`` sin duplicar."""
    from apps.proveedores.models import Proveedor

    p = ing.payload
    prov_id = ing.resultado.get("proveedor_id")
    prov = (
        Proveedor.objects.filter(pk=prov_id, id_empresa=ing.id_empresa).first()
        if prov_id
        else None
    )
    if prov is not None and _es_id(prov.referencia_externa):
        return int(prov.referencia_externa), False

    rif = _canon_rif(p.get("rif")) or (_canon_rif(prov.rif) if prov else None)
    nombre = str(p.get("proveedor") or (prov.razon_social if prov else "")).strip() or None
    if rif is None and nombre is None:
        raise NoSincronizable(
            "Indica el nombre o el RIF del proveedor para enviarlo a Odoo."
        )

    marca_prov = f"{marca}-PROV"
    clave_lock = f"rif:{rif}" if rif else f"nom:{_slug(nombre or '')}"
    with _bloqueo_partner_tx(ing.id_empresa_id, clave_lock):
        if prov is not None:
            prov.refresh_from_db(fields=["referencia_externa"])
            if _es_id(prov.referencia_externa):
                return int(prov.referencia_externa), False
        propio = _partner_por_marca(cli, marca_prov)
        if propio is not None:
            _guardar_ref_proveedor(prov, propio)
            return propio, True
        pid = _partner_por_rif(cli, rif)
        if pid is None and nombre:
            for solo_prov in (True, False):
                ids = _buscar_partner_exacto(cli, nombre, solo_proveedores=solo_prov)
                if len(ids) > 1:
                    raise NoSincronizable(
                        f"Proveedor «{nombre}» ambiguo en Odoo ({len(ids)} coincidencias): vincúlalo manualmente."
                    )
                if ids:
                    pid = ids[0]
                    break
        if pid is not None:
            _guardar_ref_proveedor(prov, pid)
            return pid, False
        if nombre is None:
            raise NoSincronizable(
                f"El RIF {rif} no existe en Odoo; indica el nombre del proveedor para crearlo."
            )
        creado = _crear_proveedor_odoo(
            cli,
            {
                "nombre": nombre,
                "rif": rif,
                "telefono": p.get("proveedor_telefono")
                or (prov.telefono if prov else None),
                "email": p.get("proveedor_email") or (prov.email if prov else None),
                "direccion": p.get("proveedor_direccion")
                or (prov.direccion if prov else None),
                "nota_cabecera": NOTA_PROVEEDOR_DE_DOCUMENTO,
            },
            marca_prov,
        )
        _guardar_ref_proveedor(prov, creado)
        return creado, True


def _push_documento_compra(
    ing: IngestaBot, conn: OdooConnector, cli, inst
) -> tuple[str, str]:
    """Empuja ``factura_proveedor`` o ``gasto`` como ``account.move`` ``in_invoice`` en borrador."""
    from apps.cuentas_por_pagar.models import CuentaPorPagar

    es_gasto = ing.kind == IngestaBot.Kind.GASTO
    cxp = None
    if not es_gasto and ing.resultado.get("cxp_id"):
        cxp = CuentaPorPagar.objects.filter(
            pk=ing.resultado["cxp_id"], id_empresa=ing.id_empresa
        ).first()
        if cxp is not None and _es_id(cxp.referencia_externa):
            return "account.move", str(cxp.referencia_externa)

    marca = _marca(ing)
    partner_id, prov_creado_odoo = _resolver_o_crear_proveedor_documento(
        ing, cli, marca
    )

    previos = cli.call(
        "account.move",
        "search",
        [[["move_type", "=", "in_invoice"], ["narration", "ilike", marca]]],
        {"limit": 1},
    )
    if previos:
        mid = int(previos[0])
        if cxp is not None and cxp.referencia_externa != str(mid):
            cxp.referencia_externa = str(mid)
            cxp.save(update_fields=["referencia_externa"])
        return "account.move", str(mid)

    p = ing.payload
    numero = (
        str(p["numero_factura"]).strip()
        if not _vacio(p.get("numero_factura"))
        else None
    )
    if numero and not prov_creado_odoo:
        ajena = _factura_proveedor_por_ref(cli, partner_id, numero)
        if ajena is not None:
            raise NoSincronizable(
                f"La factura {numero} ya existe en Odoo para ese proveedor (account.move {ajena})."
            )

    moneda_id = _moneda_odoo(cli, str(p.get("moneda") or ""))
    if moneda_id is None:
        raise NoSincronizable(f"Moneda «{p.get('moneda')}» no encontrada en Odoo.")

    campos_move = _campos_modelo_opcional(cli, "account.move")
    if campos_move is not None:
        requeridos = {
            "move_type",
            "partner_id",
            "ref",
            "invoice_date",
            "currency_id",
            "invoice_line_ids",
            "narration",
        }
        faltan = requeridos - campos_move
        if faltan:
            raise NoSincronizable(
                "Odoo no tiene los campos de factura esperados ("
                + ", ".join(sorted(faltan))
                + ")."
            )
    campos_linea = _campos_modelo_opcional(cli, "account.move.line")
    con_impuestos = campos_linea is None or "tax_ids" in campos_linea
    admite_vencimiento = campos_move is None or "invoice_date_due" in campos_move

    monto_total = _decimal_seguro(p.get("monto_total"), "monto_total")
    base = p.get("base_imponible")
    monto = monto_total
    if not _vacio(base):
        base_dec = _decimal_seguro(base, "base_imponible")
        if base_dec > 0:
            monto = base_dec

    etiqueta = numero or f"S/N-{str(ing.pk)[-8:]}"
    proveedor_txt = (
        str(p["proveedor"]).strip() if not _vacio(p.get("proveedor")) else "proveedor"
    )
    notas = [
        "Gasto de consumo pagado al contado (sin pago asociado: contabilidad lo concilia)"
        if es_gasto
        else f"Factura proveedor {etiqueta}",
        f"Documento {numero}" if es_gasto and numero else "",
        f"Categoría {p['categoria']}"
        if es_gasto and not _vacio(p.get("categoria"))
        else "",
        f"Control {p['numero_control']}" if not _vacio(p.get("numero_control")) else "",
        f"IVA {p['iva']}" if not _vacio(p.get("iva")) else "",
        f"Monto total {p['monto_total']} {p['moneda']}",
        f"Orden {p['orden_ref']}" if not _vacio(p.get("orden_ref")) else "",
        str(p["notas"]) if not _vacio(p.get("notas")) else "",
    ]
    if not _vacio(p.get("concepto")):
        concepto = str(p["concepto"]).strip()
    else:
        concepto = (
            f"Compra en {proveedor_txt}"
            if es_gasto
            else f"Factura proveedor {etiqueta}"
        )

    # Conversión intencional en la frontera XML-RPC hacia Odoo (quantity/price_unit son Float).
    linea: dict[str, Any] = {
        "name": concepto,
        "quantity": 1.0,
        "price_unit": float(monto),
    }
    if con_impuestos:
        linea["tax_ids"] = [(6, 0, [])]

    fecha_vence = (
        None
        if es_gasto or not admite_vencimiento
        else _fecha_iso(p.get("fecha_vencimiento"))
    )
    vals = _vals(
        move_type="in_invoice",
        partner_id=partner_id,
        ref=etiqueta,
        invoice_date=_fecha_iso(p.get("fecha_emision")) or str(p["fecha_emision"]),
        invoice_date_due=fecha_vence,
        currency_id=moneda_id,
        narration=f"{marca} · " + " · ".join(x for x in notas if x),
        invoice_line_ids=[(0, 0, linea)],
    )
    mid = _id_creado(cli.call("account.move", "create", [vals]))
    if cxp is not None:
        cxp.referencia_externa = str(mid)
        cxp.save(update_fields=["referencia_externa"])
    return "account.move", str(mid)


_PUSHERS = {
    IngestaBot.Kind.CONTACTO: _push_contacto,
    IngestaBot.Kind.PEDIDO: _push_pedido,
    IngestaBot.Kind.PAGO: _push_pago,
    IngestaBot.Kind.PAGO_PROVEEDOR: _push_pago,
    IngestaBot.Kind.PROVEEDOR: _push_proveedor,
    IngestaBot.Kind.FACTURA_PROVEEDOR: _push_documento_compra,
    IngestaBot.Kind.GASTO: _push_documento_compra,
}


def _es_error_red(exc: BaseException) -> bool:
    causa = exc.__cause__
    return isinstance(causa, (TimeoutError, OSError, xmlrpc.client.ProtocolError))


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
    if inst is None or inst.get_config().get("empujar_bots") is not True:
        # Opt-in explícito: mientras CxC sea quien escribe en Odoo, Omni NO debe empujar (se duplicaría).
        return ing
    if not debe_sincronizar(ing):
        _anotar(ing, "Faltan datos: complétala antes de enviarla a Odoo.")
        return ing
    try:
        inst_escritura = _InstanciaEscritura(inst)
        inst_escritura.get_config()  # valida par write_user/write_api_key antes de conectar
        conn = OdooConnector(inst_escritura)
        cli = conn._get_client()
        modelo, oid = _PUSHERS[ing.kind](ing, conn, cli, inst)
    except NoSincronizable as e:
        _anotar(ing, str(e))
        return ing
    except ConnectorConnectionError as e:
        logger.warning("Odoo no disponible al sincronizar ingesta %s", ing.pk)
        raise ErrorTransitorio("Odoo no disponible") from e
    except OdooCallError as e:
        if _es_error_red(e):
            logger.warning("Fallo de red con Odoo al sincronizar ingesta %s", ing.pk)
            raise ErrorTransitorio("Odoo no disponible") from e
        logger.exception("Falló el envío a Odoo de la ingesta %s", ing.pk)
        _anotar(ing, "Odoo rechazó el envío; revisa los datos o reintenta.")
        return ing
    except ConnectorError:
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
