"""Helpers de seeding para los tests de operación (Fase 3)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone

from apps.cxc_lubrikca.models import (
    BandejaFacturacion,
    DescuentoMarcaCategoria,
    LineaPedidoLubrikca,
    MetodoPago,
    PagoLubrikca,
    PedidoLubrikca,
    PrecioListaLubrikca,
    ReglaRecurrencia,
)
from apps.cxc_lubrikca.services.bridge import LISTA_BCV_DEFAULT, LISTA_USD_DEFAULT
from apps.finanzas.models import Moneda as FinMoneda
from apps.finanzas.models import TasaCambio


def crear_pedido(empresa, **kwargs):
    defaults = dict(
        so_id="SO1",
        cliente_externo_id="C1",
        cliente_nombre="Cliente 1",
        vendedor_email="rep@lubrikca.com",
        fecha=date(2026, 6, 1),
        fecha_entrega=date(2026, 6, 5),
        monto_total=Decimal("100"),
        lista_precios=LISTA_BCV_DEFAULT,
        es_primera_compra=False,
    )
    defaults.update(kwargs)
    return PedidoLubrikca.objects.create(empresa=empresa, **defaults)


def crear_linea(empresa, pedido, **kwargs):
    defaults = dict(
        linea_id="L1",
        producto="P1",
        marca="Sinoco",
        categoria="*",
        cantidad=Decimal("1"),
        precio_unitario=Decimal("100"),
    )
    defaults.update(kwargs)
    return LineaPedidoLubrikca.objects.create(
        empresa=empresa, pedido=pedido, **defaults
    )


def crear_precio(empresa, producto="P1", lista=LISTA_USD_DEFAULT, precio="100"):
    return PrecioListaLubrikca.objects.create(
        empresa=empresa, producto=producto, lista=lista, precio=Decimal(precio)
    )


def crear_pago(empresa, **kwargs):
    defaults = dict(
        pago_id="PG1",
        cliente_externo_id="C1",
        monto=Decimal("94"),
        moneda="USD",
        metodo_pago="ZELLE",
        fecha_pago=timezone.make_aware(datetime(2026, 6, 5, 10, 0)),
        vendedor_email="rep@lubrikca.com",
    )
    defaults.update(kwargs)
    return PagoLubrikca.objects.create(empresa=empresa, **defaults)


def crear_bandeja(empresa, pedido, total_motor="100", **kwargs):
    """Crea una BandejaFacturacion directa (sin pasar por el motor)."""
    defaults = dict(
        lista_aplicada=pedido.lista_precios,
        precio_base_calculado=Decimal(total_motor),
        total_motor=Decimal(total_motor),
    )
    defaults.update(kwargs)
    return BandejaFacturacion.objects.create(
        empresa=empresa, pedido=pedido, **defaults
    )


def crear_metodo(empresa, codigo="ZELLE", moneda="USD", tipo_tasa="N_A", es_contado=True):
    return MetodoPago.objects.create(
        empresa=empresa,
        codigo=codigo,
        nombre=codigo,
        moneda=moneda,
        tipo_tasa=tipo_tasa,
        es_contado=es_contado,
    )


def crear_descuento(empresa, marca="Sinoco", categoria="*", porcentaje="0.03"):
    return DescuentoMarcaCategoria.objects.create(
        empresa=empresa,
        marca=marca,
        categoria=categoria,
        porcentaje=Decimal(porcentaje),
        vigencia_desde=date(2026, 1, 1),
    )


def crear_recompra(empresa, valor="0.03"):
    return ReglaRecurrencia.objects.create(
        empresa=empresa,
        condicion="recompra",
        tipo_beneficio="porcentaje",
        valor=Decimal(valor),
        vigencia_desde=date(2026, 1, 1),
    )


def cargar_tasas(empresa, fecha=date(2026, 6, 5), bcv="36.0", binance="40.0"):
    """Carga las tasas USD→VES (BCV global y Binance específica) para la fecha."""
    usd, _ = FinMoneda.objects.get_or_create(
        codigo_iso="USD", defaults={"nombre": "Dólar", "simbolo": "$"}
    )
    ves, _ = FinMoneda.objects.get_or_create(
        codigo_iso="VES", defaults={"nombre": "Bolívar", "simbolo": "Bs"}
    )
    TasaCambio.objects.create(
        id_empresa=None,
        id_moneda_origen=usd,
        id_moneda_destino=ves,
        tipo_tasa="OFICIAL_BCV",
        valor_tasa=Decimal(bcv),
        fecha_tasa=fecha,
    )
    TasaCambio.objects.create(
        id_empresa=empresa,
        id_moneda_origen=usd,
        id_moneda_destino=ves,
        tipo_tasa="PROMEDIO_MERCADO",
        valor_tasa=Decimal(binance),
        fecha_tasa=fecha,
    )
