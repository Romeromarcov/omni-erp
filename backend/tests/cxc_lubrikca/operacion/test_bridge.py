"""Tests del bridge Django→motor y recálculo de bandeja (Fase 3)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.cxc_lubrikca.models import BandejaFacturacion
from apps.cxc_lubrikca.services.bridge import (
    LISTA_USD_DEFAULT,
    BridgeError,
    construir_engine_inputs,
    recalcular_bandeja,
)
from apps.cxc_lubrikca.services.captura import registrar_vinculacion

from . import helpers as h

pytestmark = pytest.mark.django_db


def test_recalcular_bandeja_sin_abonos_usa_lista_nacimiento(empresa_a):
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    h.crear_precio(empresa_a, lista=pedido.lista_precios, precio="120")

    bandeja = recalcular_bandeja(pedido)

    assert bandeja.lista_aplicada == pedido.lista_precios
    assert bandeja.precio_base_calculado == Decimal("120.00")
    assert bandeja.candidata_a_cierre is False
    assert BandejaFacturacion.objects.filter(pedido=pedido).count() == 1


def test_recalcular_bandeja_recompra_contado_6pct(empresa_a, user_a):
    # Espejo del caso del motor: Sinoco 3% recompra + 3% contado sobre $100,
    # abono USD de $94 → total_motor 94.00.
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    h.crear_precio(empresa_a, lista=LISTA_USD_DEFAULT, precio="100")
    h.crear_metodo(empresa_a, tipo_tasa="N_A")
    h.crear_descuento(empresa_a)
    h.crear_recompra(empresa_a)
    h.cargar_tasas(empresa_a)

    pago = h.crear_pago(empresa_a, monto=Decimal("94"))
    registrar_vinculacion(
        pedido=pedido,
        pago=pago,
        monto_aplicado=Decimal("94"),
        hora_pago_confirmada=pago.fecha_pago,
        usuario=user_a,
    )

    bandeja = BandejaFacturacion.objects.get(pedido=pedido)
    assert bandeja.lista_aplicada == LISTA_USD_DEFAULT
    assert bandeja.precio_base_calculado == Decimal("100.00")
    assert bandeja.total_descuentos == Decimal("6.00")
    assert bandeja.total_motor == Decimal("94.00")
    assert bandeja.candidata_a_cierre is True
    origenes = {d["origen"] for d in bandeja.descuentos_detalle}
    assert origenes == {"recurrencia", "contado"}


def test_construir_engine_inputs_mapea_config_del_tenant(empresa_a):
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    h.crear_descuento(empresa_a)
    h.crear_recompra(empresa_a)

    inp = construir_engine_inputs(pedido, fecha_calculo=date(2026, 6, 8))

    assert inp.orden.so_id == "SO1"
    assert len(inp.lineas) == 1
    assert len(inp.descuentos) == 1
    assert len(inp.reglas_recurrencia) == 1
    # regla_id es el str(id) de la fila Django (determinismo del effective dating).
    assert inp.descuentos[0].regla_id


def test_recalcular_sin_precio_lanza_bridge_error(empresa_a):
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)  # sin PrecioListaLubrikca sembrado
    with pytest.raises(BridgeError, match="precio"):
        recalcular_bandeja(pedido)


def test_construir_engine_inputs_incluye_bcv_promo_feriado(empresa_a):
    from datetime import date as _date

    from apps.cxc_lubrikca.models import (
        DescuentoBCVCompleto,
        Feriado,
        PromocionPrimeraCompra,
    )

    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    DescuentoBCVCompleto.objects.create(
        empresa=empresa_a, porcentaje=Decimal("0.15"), vigencia_desde=_date(2026, 1, 1)
    )
    PromocionPrimeraCompra.objects.create(
        empresa=empresa_a, producto="LIGA", vigencia_desde=_date(2026, 1, 1)
    )
    Feriado.objects.create(
        empresa=empresa_a, fecha=_date(2026, 6, 24), descripcion="Carabobo"
    )

    inp = construir_engine_inputs(pedido, fecha_calculo=date(2026, 6, 8))

    assert len(inp.descuento_bcv_diario) == 1
    assert len(inp.promociones_primera_compra) == 1
    assert len(inp.feriados_tabla) == 1
    assert inp.descuento_bcv_diario[0].porcentaje == Decimal("0.15")
    assert inp.promociones_primera_compra[0].producto == "LIGA"


def test_str_de_los_modelos_operacion(empresa_a):
    from apps.cxc_lubrikca.models import (
        BandejaFacturacion,
        PagoLubrikca,
        PrecioListaLubrikca,
        Vinculacion,
    )

    pedido = h.crear_pedido(empresa_a)
    linea = h.crear_linea(empresa_a, pedido)
    precio = h.crear_precio(empresa_a)
    pago = h.crear_pago(empresa_a)
    h.crear_metodo(empresa_a)
    h.cargar_tasas(empresa_a)
    from apps.cxc_lubrikca.services.captura import registrar_vinculacion

    h.crear_precio(empresa_a, lista=pedido.lista_precios, precio="100")
    vinc = registrar_vinculacion(
        pedido=pedido, pago=pago, monto_aplicado=Decimal("50"),
        hora_pago_confirmada=pago.fecha_pago, usuario=None,
    )
    bandeja = pedido.bandeja

    assert str(pedido)
    assert str(linea)
    assert str(precio)
    assert str(pago)
    assert isinstance(vinc, Vinculacion) and str(vinc)
    assert isinstance(bandeja, BandejaFacturacion) and str(bandeja)
    assert isinstance(PrecioListaLubrikca.objects.first(), PrecioListaLubrikca)
    assert PagoLubrikca.objects.exists()


def test_db_price_resolver_con_dict_prefetch(empresa_a):
    from apps.cxc_lubrikca.services.price_resolver_db import DBPriceResolver

    resolver = DBPriceResolver(empresa_a, precios={("P1", "4"): Decimal("99")})
    assert resolver.precio("P1", "4") == Decimal("99")
    with pytest.raises(KeyError):
        resolver.precio("NOPE", "4")


def test_recalcular_es_idempotente_upsert(empresa_a):
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    h.crear_precio(empresa_a, lista=pedido.lista_precios, precio="100")

    b1 = recalcular_bandeja(pedido)
    b2 = recalcular_bandeja(pedido)

    assert b1.pk == b2.pk
    assert BandejaFacturacion.objects.filter(pedido=pedido).count() == 1
