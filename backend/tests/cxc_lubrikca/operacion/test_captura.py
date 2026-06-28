"""Tests del servicio de captura de vinculaciones (Fase 3)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.cxc_lubrikca.models import BandejaFacturacion, Vinculacion
from apps.cxc_lubrikca.services.captura import (
    VinculacionError,
    registrar_vinculacion,
)

from . import helpers as h

pytestmark = pytest.mark.django_db


def _seed(empresa, monto_pago="94"):
    pedido = h.crear_pedido(empresa)
    h.crear_linea(empresa, pedido)
    h.crear_precio(empresa, lista="4", precio="100")
    h.crear_metodo(empresa, tipo_tasa="N_A")
    h.crear_descuento(empresa)
    h.crear_recompra(empresa)
    h.cargar_tasas(empresa)
    pago = h.crear_pago(empresa, monto=Decimal(monto_pago))
    return pedido, pago


def test_happy_path_estampa_tasas_y_congela_equivalentes(empresa_a, user_a):
    pedido, pago = _seed(empresa_a)

    vinc = registrar_vinculacion(
        pedido=pedido,
        pago=pago,
        monto_aplicado=Decimal("94"),
        hora_pago_confirmada=pago.fecha_pago,
        usuario=user_a,
    )

    assert vinc.tasa_bcv_aplicada == Decimal("36.00000000")
    assert vinc.tasa_binance_aplicada == Decimal("40.00000000")
    # Abono USD → equivalentes USD = monto; VES = monto * tasa.
    assert vinc.equiv_usd_bcv == Decimal("94.000000")
    assert vinc.equiv_ves_bcv == Decimal("3384.000000")  # 94 * 36
    assert vinc.equiv_ves_binance == Decimal("3760.000000")  # 94 * 40
    assert vinc.confirmado_por_id == user_a.pk
    pago.refresh_from_db()
    assert pago.vinculado is True
    # La bandeja se recalculó.
    assert BandejaFacturacion.objects.filter(pedido=pedido).exists()


def test_ves_abono_calcula_equivalentes_usd(empresa_a, user_a):
    pedido, _ = _seed(empresa_a)
    # El abono VES con método tipo_tasa=BCV hace ruta BCV pura → el motor
    # reselecciona la lista BCV ("5"); hay que tener su precio sembrado.
    h.crear_precio(empresa_a, lista="5", precio="100")
    pago = h.crear_pago(
        empresa_a, pago_id="PG-VES", monto=Decimal("3600"), moneda="VES"
    )
    h.crear_metodo(empresa_a, codigo="PAGO_MOVIL", moneda="VES", tipo_tasa="BCV")
    pago.metodo_pago = "PAGO_MOVIL"
    pago.save(update_fields=["metodo_pago"])

    vinc = registrar_vinculacion(
        pedido=pedido,
        pago=pago,
        monto_aplicado=Decimal("3600"),
        hora_pago_confirmada=pago.fecha_pago,
        usuario=user_a,
    )
    assert vinc.tipo_tasa_abono == "BCV"
    assert vinc.equiv_usd_bcv == Decimal("100.000000")  # 3600 / 36
    assert vinc.equiv_usd_binance == Decimal("90.000000")  # 3600 / 40


def test_metodo_inexistente_usa_na(empresa_a, user_a):
    # Pago con un código de método que NO existe en config → tipo_tasa N_A.
    pedido, _ = _seed(empresa_a)
    pago = h.crear_pago(empresa_a, pago_id="PG-SINMET", metodo_pago="DESCONOCIDO")
    vinc = registrar_vinculacion(
        pedido=pedido,
        pago=pago,
        monto_aplicado=Decimal("50"),
        hora_pago_confirmada=pago.fecha_pago,
        usuario=user_a,
    )
    assert vinc.tipo_tasa_abono == "N_A"


def test_aplicacion_parcial_no_marca_vinculado(empresa_a, user_a):
    pedido, pago = _seed(empresa_a, monto_pago="94")
    registrar_vinculacion(
        pedido=pedido,
        pago=pago,
        monto_aplicado=Decimal("40"),
        hora_pago_confirmada=pago.fecha_pago,
        usuario=user_a,
    )
    pago.refresh_from_db()
    assert pago.vinculado is False


def test_solo_falta_tasa_binance(empresa_a, user_a):
    # Carga solo BCV: el mensaje debe mencionar solo Binance.
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    h.crear_metodo(empresa_a)
    from datetime import date as _date

    from apps.finanzas.models import Moneda as FinMoneda
    from apps.finanzas.models import TasaCambio

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
        valor_tasa=Decimal("36"),
        fecha_tasa=_date(2026, 6, 5),
    )
    pago = h.crear_pago(empresa_a)
    with pytest.raises(VinculacionError, match="Binance"):
        registrar_vinculacion(
            pedido=pedido,
            pago=pago,
            monto_aplicado=Decimal("94"),
            hora_pago_confirmada=pago.fecha_pago,
            usuario=user_a,
        )


def test_monto_no_positivo_falla(empresa_a, user_a):
    pedido, pago = _seed(empresa_a)
    with pytest.raises(VinculacionError, match="mayor a cero"):
        registrar_vinculacion(
            pedido=pedido,
            pago=pago,
            monto_aplicado=Decimal("0"),
            hora_pago_confirmada=pago.fecha_pago,
            usuario=user_a,
        )


def test_distinto_cliente_falla(empresa_a, user_a):
    pedido, _ = _seed(empresa_a)
    pago = h.crear_pago(empresa_a, pago_id="PG-X", cliente_externo_id="OTRO")
    with pytest.raises(VinculacionError, match="mismo cliente"):
        registrar_vinculacion(
            pedido=pedido,
            pago=pago,
            monto_aplicado=Decimal("50"),
            hora_pago_confirmada=pago.fecha_pago,
            usuario=user_a,
        )


def test_sobre_vinculacion_falla(empresa_a, user_a):
    pedido, pago = _seed(empresa_a, monto_pago="94")
    # Primera vinculación consume 90; quedan 4.
    registrar_vinculacion(
        pedido=pedido,
        pago=pago,
        monto_aplicado=Decimal("90"),
        hora_pago_confirmada=pago.fecha_pago,
        usuario=user_a,
    )
    with pytest.raises(VinculacionError, match="Sobre-vinculación"):
        registrar_vinculacion(
            pedido=pedido,
            pago=pago,
            monto_aplicado=Decimal("10"),
            hora_pago_confirmada=pago.fecha_pago,
            usuario=user_a,
        )


def test_sin_tasa_cargada_falla(empresa_a, user_a):
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    h.crear_metodo(empresa_a)
    pago = h.crear_pago(empresa_a)
    # NO se cargan tasas.
    with pytest.raises(VinculacionError, match="No hay tasa"):
        registrar_vinculacion(
            pedido=pedido,
            pago=pago,
            monto_aplicado=Decimal("94"),
            hora_pago_confirmada=pago.fecha_pago,
            usuario=user_a,
        )


def test_distinta_empresa_falla(empresa_a, empresa_b, user_a):
    pedido, _ = _seed(empresa_a)
    pago_b = h.crear_pago(empresa_b)
    with pytest.raises(VinculacionError, match="misma empresa"):
        registrar_vinculacion(
            pedido=pedido,
            pago=pago_b,
            monto_aplicado=Decimal("50"),
            hora_pago_confirmada=pago_b.fecha_pago,
            usuario=user_a,
        )
