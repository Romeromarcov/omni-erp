"""Sync Odoo → espejo CxC Lubrikca (Fase 5, SOLO LECTURA hacia Odoo).

Pobla las tablas-espejo del motor determinístico
(``PedidoLubrikca``, ``LineaPedidoLubrikca``, ``PrecioListaLubrikca``,
``PagoLubrikca``) y las entradas de conciliación
(``PedidoLubrikca.monto_facturado`` / ``.ncs_facturadas``) a partir de lo que el
``LubrikcaOdooReader`` extrae de Odoo.

Separación de mundos de datos (regla inviolable de la fase): el sync NUNCA crea,
actualiza ni borra ``Vinculacion``, ``BandejaFacturacion`` ni
``ConciliacionLubrikca`` — esas son trabajo humano / derivadas del motor. El sync
solo refresca el espejo y los insumos de conciliación.

Idempotente: cada entidad se hace *upsert* por su clave natural dentro de la
empresa (multi-tenant, R-CODE-1). Dinero/cantidad son Decimal (R-CODE-4).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.cxc_lubrikca.models import (
    LineaPedidoLubrikca,
    PagoLubrikca,
    PedidoLubrikca,
    PrecioListaLubrikca,
)
from apps.cxc_lubrikca.services.odoo_reader import (
    LubrikcaOdooReader,
    execute_para_empresa,
)


class SyncError(Exception):
    """Error de sincronización Odoo → espejo."""


def _parse_fecha(value) -> object | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _parse_datetime(value):
    """Parsea datetime de Odoo a aware datetime (o ahora si falta)."""
    if not value:
        return timezone.now()
    s = str(value)
    fmt = "%Y-%m-%d %H:%M:%S" if len(s) > 10 else "%Y-%m-%d"
    try:
        dt = datetime.strptime(s[:19], fmt)
    except (ValueError, TypeError):
        return timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


@transaction.atomic
def sincronizar_desde_odoo(empresa, reader: LubrikcaOdooReader, *, desde=None) -> dict:
    """Refresca el espejo de la empresa desde Odoo. Devuelve conteos.

    NO toca Vinculacion/BandejaFacturacion/ConciliacionLubrikca.
    """
    pedidos = reader.leer_pedidos(desde=desde)
    so_names = [p["so_id"] for p in pedidos if p.get("so_id")]

    entregas = reader.leer_entregas(so_names)
    facturas = reader.leer_facturas(so_names)
    lineas = reader.leer_lineas(so_names)
    pagos = reader.leer_pagos(desde=desde)

    n_pedidos = _upsert_pedidos(empresa, pedidos, entregas, facturas)
    n_lineas, n_precios = _upsert_lineas_y_precios(empresa, lineas)
    n_pagos = _upsert_pagos(empresa, pagos)

    return {
        "pedidos": n_pedidos,
        "lineas": n_lineas,
        "pagos": n_pagos,
        "precios": n_precios,
        "facturas": len(facturas),
    }


def _upsert_pedidos(empresa, pedidos, entregas, facturas) -> int:
    count = 0
    for p in pedidos:
        so_id = p.get("so_id")
        if not so_id:
            continue
        entrega = entregas.get(so_id, {})
        factura = facturas.get(so_id, {})

        estado_entrega = p.get("estado_entrega", "") or ""
        entregada_completa = estado_entrega == "full"
        # El plazo de contado solo arranca con la entrega completa.
        fecha_entrega = (
            _parse_fecha(entrega.get("fecha_entrega")) if entregada_completa else None
        )
        monto_facturado = factura.get("monto_facturado_usd")
        ncs = factura.get("ncs", Decimal("0"))
        invoice_status = p.get("invoice_status", "")
        facturada = invoice_status == "invoiced" or bool(
            monto_facturado and monto_facturado > 0
        )

        PedidoLubrikca.objects.update_or_create(
            empresa=empresa,
            so_id=so_id,
            defaults={
                "cliente_externo_id": p.get("cliente_externo_id", "") or "",
                "vendedor_email": p.get("vendedor_email", "") or "",
                "fecha": _parse_fecha(p.get("fecha")) or timezone.now().date(),
                "fecha_entrega": fecha_entrega,
                "monto_total": p.get("monto_total", Decimal("0")),
                "lista_precios": p.get("lista_precios", "") or "",
                "es_primera_compra": bool(p.get("es_primera_compra", False)),
                "facturada": facturada,
                "factura_id": factura.get("factura_id", "") or "",
                "monto_facturado": monto_facturado,
                "ncs_facturadas": ncs or Decimal("0"),
                "estado_entrega": estado_entrega,
                "entregada_completa": entregada_completa,
                "tiene_devolucion": bool(entrega.get("tiene_devolucion", False)),
            },
        )
        count += 1
    return count


def _upsert_lineas_y_precios(empresa, lineas) -> tuple[int, int]:
    # Mapa so_id → pedido (solo de esta empresa) para vincular las líneas.
    so_ids = {ln.get("so_id") for ln in lineas if ln.get("so_id")}
    pedidos_por_so = {
        ped.so_id: ped
        for ped in PedidoLubrikca.objects.filter(empresa=empresa, so_id__in=so_ids)
    }

    n_lineas = 0
    n_precios = 0
    for ln in lineas:
        pedido = pedidos_por_so.get(ln.get("so_id"))
        if pedido is None:
            # Línea de una SO que no está en el espejo de esta empresa: se omite.
            continue
        LineaPedidoLubrikca.objects.update_or_create(
            empresa=empresa,
            pedido=pedido,
            linea_id=ln.get("linea_id", "") or "",
            defaults={
                "producto": ln.get("producto", "") or "",
                "marca": ln.get("marca", "*") or "*",
                "categoria": ln.get("categoria", "*") or "*",
                "cantidad": ln.get("cantidad", Decimal("0")),
                "precio_unitario": ln.get("precio_unitario", Decimal("0")),
                "cantidad_entregada": ln.get("cantidad_entregada", Decimal("0")),
            },
        )
        n_lineas += 1

        # Precio de lista: poblar el precio del producto en la lista de su pedido,
        # para que el price resolver lo encuentre. (Odoo 18 removió price_get();
        # para ambas listas USD/BCV se usa el precio de la línea ya sincronizado.)
        producto = ln.get("producto", "") or ""
        lista = pedido.lista_precios or ""
        if producto and lista:
            _, created = PrecioListaLubrikca.objects.update_or_create(
                empresa=empresa,
                producto=producto,
                lista=lista,
                defaults={"precio": ln.get("precio_unitario", Decimal("0"))},
            )
            if created:
                n_precios += 1
    return n_lineas, n_precios


def _upsert_pagos(empresa, pagos) -> int:
    count = 0
    for pg in pagos:
        pago_id = pg.get("pago_id")
        if not pago_id:
            continue
        PagoLubrikca.objects.update_or_create(
            empresa=empresa,
            pago_id=pago_id,
            defaults={
                "cliente_externo_id": pg.get("cliente_externo_id", "") or "",
                "monto": pg.get("monto", Decimal("0")),
                "moneda": pg.get("moneda", "USD") or "USD",
                "metodo_pago": pg.get("metodo_pago", "") or "",
                "fecha_pago": _parse_datetime(pg.get("fecha_pago")),
                "vendedor_email": pg.get("vendedor_email", "") or "",
            },
        )
        count += 1
    return count


def sincronizar_empresa(empresa, *, desde=None) -> dict:
    """Conveniencia: arma el reader de producción y sincroniza la empresa."""
    reader = LubrikcaOdooReader(execute_para_empresa(empresa))
    return sincronizar_desde_odoo(empresa, reader, desde=desde)
