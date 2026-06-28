"""Tests de utilidades puras del motor — decimal_utils, effective_dating,
equivalents, rutas y conciliación pura (clasificar_diferencia).

Port puro de ``CxC_Lubrikca/tests/test_config_and_utils.py``: se omiten los tests
de ``AppConfig.from_env`` / ``BinanceConfig`` / ``alerts`` (infra con env-loading
y Telegram, no portados a la capa motor) y se añade una prueba determinística de
``clasificar_diferencia`` (las tres bandas + la lógica neto = monto − ncs), ya
que el test de conciliación del fuente estaba acoplado a infra Odoo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.cxc_lubrikca.services.motor.config import (
    EngineConfig,
    HourAuditConfig,
    ReconciliationConfig,
    default_engine_config,
    default_hour_audit_config,
    default_reconciliation_config,
)
from apps.cxc_lubrikca.services.motor.price_resolver import DictPriceResolver
from apps.cxc_lubrikca.services.motor.decimal_utils import q2, q6, to_decimal
from apps.cxc_lubrikca.services.motor.effective_dating import (
    descuento_vigente,
    promocion_primera_compra_vigente,
    regla_recurrencia_vigente,
    tasa_bcv_completo_vigente,
)
from apps.cxc_lubrikca.services.motor.equivalents import (
    calcular_equivalentes,
    congelar_en_vinculacion,
    es_ruta_bcv_pura,
    valor_pagado_usd,
)
from apps.cxc_lubrikca.services.motor.models import (
    Condicion,
    DescuentoMarcaCategoria,
    Moneda,
    ResultadoConciliacion,
    TipoDescuento,
    TipoTasa,
)
from apps.cxc_lubrikca.services.motor.reconcile import clasificar_diferencia

from . import builders as b

pytestmark = pytest.mark.unit


# --- config defaults ---------------------------------------------------------
def test_config_defaults() -> None:
    assert default_engine_config() == EngineConfig(
        cash_window_business_days=3,
        bcv_complete_formula="differential_over_binance",
        lista_usd="USD",
        lista_bcv="BCV",
    )
    assert default_reconciliation_config() == ReconciliationConfig(
        tolerance_rounding=Decimal("0.01"), tolerance_red=Decimal("1.00")
    )
    assert default_hour_audit_config() == HourAuditConfig(
        threshold_minutes=60, rate_swing_pct=Decimal("0.03")
    )


# --- price_resolver ----------------------------------------------------------
def test_price_resolver_set_y_get() -> None:
    r = DictPriceResolver({})
    r.set_precio("P1", "USD", Decimal("9.99"))
    assert r.precio("P1", "USD") == Decimal("9.99")


def test_price_resolver_sin_precio_lanza_keyerror() -> None:
    r = DictPriceResolver({})
    with pytest.raises(KeyError, match="Sin precio"):
        r.precio("NADA", "USD")


# --- decimal_utils -----------------------------------------------------------
def test_to_decimal_acepta_tipos_seguros() -> None:
    assert to_decimal(5) == Decimal("5")
    assert to_decimal("5.5") == Decimal("5.5")
    assert to_decimal(Decimal("2")) == Decimal("2")


def test_to_decimal_rechaza_bool_y_float() -> None:
    with pytest.raises(TypeError):
        to_decimal(True)
    with pytest.raises(TypeError):
        to_decimal(1.5)


def test_quantize() -> None:
    assert q2(Decimal("1.005")) == Decimal("1.01")
    assert q6(Decimal("1.0000005")) == Decimal("1.000001")


# --- effective_dating --------------------------------------------------------
def _d(regla_id: str, marca: str, categoria: str, pct: str) -> DescuentoMarcaCategoria:
    return DescuentoMarcaCategoria(
        regla_id=regla_id, marca=marca, categoria=categoria,
        tipo_descuento=TipoDescuento.CONTADO, porcentaje=Decimal(pct),
        vigencia_desde=date(2026, 1, 1),
    )


def test_descuento_categoria_exacta_gana_sobre_comodin() -> None:
    reglas = [
        _d("A", "Global Oil", "*", "0.06"),
        _d("B", "Global Oil", "Comercial sintéticos", "0.08"),
    ]
    elegido = descuento_vigente(
        reglas, marca="Global Oil", categoria="Comercial sintéticos",
        tipo=TipoDescuento.CONTADO, fecha=date(2026, 6, 1),
    )
    assert elegido is not None and elegido.regla_id == "B"


def test_descuento_fuera_de_vigencia_no_aplica() -> None:
    regla = _d("A", "Sinoco", "*", "0.03")
    regla.vigencia_hasta = date(2026, 3, 1)
    elegido = descuento_vigente(
        [regla], marca="Sinoco", categoria="*", tipo=TipoDescuento.CONTADO,
        fecha=date(2026, 6, 1),
    )
    assert elegido is None


def test_descuento_inactivo_no_aplica() -> None:
    regla = _d("A", "Sinoco", "*", "0.03")
    regla.activo = False
    assert descuento_vigente(
        [regla], marca="Sinoco", categoria="*", tipo=TipoDescuento.CONTADO,
        fecha=date(2026, 6, 1),
    ) is None


def test_descuento_antes_de_vigencia_no_aplica() -> None:
    regla = _d("A", "Sinoco", "*", "0.03")
    regla.vigencia_desde = date(2026, 7, 1)
    assert descuento_vigente(
        [regla], marca="Sinoco", categoria="*", tipo=TipoDescuento.CONTADO,
        fecha=date(2026, 6, 1),
    ) is None


def test_descuento_empate_rompe_por_menor_pct_luego_regla_id() -> None:
    # Misma especificidad y vigencia: gana el menor porcentaje (conservador),
    # luego el regla_id menor para determinismo.
    reglas = [
        _d("B", "Sinoco", "*", "0.05"),
        _d("A", "Sinoco", "*", "0.05"),
    ]
    elegido = descuento_vigente(
        reglas, marca="Sinoco", categoria="*", tipo=TipoDescuento.CONTADO,
        fecha=date(2026, 6, 1),
    )
    assert elegido is not None and elegido.regla_id == "A"


def test_descuento_sin_match_devuelve_none() -> None:
    assert descuento_vigente(
        [], marca="X", categoria="Y", tipo=TipoDescuento.CONTADO,
        fecha=date(2026, 6, 1),
    ) is None


def test_recurrencia_vigente_selecciona_mas_reciente() -> None:
    vieja = b.regla_recompra("0.03", desde=date(2026, 1, 1))
    nueva = b.regla_recompra("0.04", desde=date(2026, 5, 1))
    elegido = regla_recurrencia_vigente(
        [vieja, nueva], condicion=Condicion.RECOMPRA, fecha=date(2026, 6, 1),
    )
    assert elegido is not None and elegido.valor == Decimal("0.04")


def test_recurrencia_sin_match_none() -> None:
    assert regla_recurrencia_vigente(
        [], condicion=Condicion.PRIMERA_COMPRA, fecha=date(2026, 6, 1)
    ) is None


def test_promocion_primera_compra_vigente_mas_reciente() -> None:
    vieja = b.promo_primera("LIGA", desde=date(2026, 1, 1))
    nueva = b.promo_primera("FILTRO", desde=date(2026, 5, 1))
    elegida = promocion_primera_compra_vigente(
        [vieja, nueva], fecha=date(2026, 6, 1)
    )
    assert elegida is not None and elegida.producto == "FILTRO"


def test_promocion_primera_compra_sin_match_none() -> None:
    assert promocion_primera_compra_vigente([], fecha=date(2026, 6, 1)) is None


def test_tasa_bcv_completo_vigente_mas_reciente_luego_menor_pct() -> None:
    vieja = b.regla_bcv_completo("0.10", desde=date(2026, 1, 1))
    nueva = b.regla_bcv_completo("0.15", desde=date(2026, 5, 1))
    assert tasa_bcv_completo_vigente(
        [vieja, nueva], fecha=date(2026, 6, 1)
    ) == Decimal("0.15")


def test_tasa_bcv_completo_sin_match_none() -> None:
    assert tasa_bcv_completo_vigente([], fecha=date(2026, 6, 1)) is None


# --- equivalents -------------------------------------------------------------
def test_equivalentes_ves() -> None:
    eq = calcular_equivalentes(Decimal("3600"), Moneda.VES, Decimal("36"),
                               Decimal("40"))
    assert eq.equiv_usd_bcv == Decimal("100.000000")
    assert eq.equiv_usd_binance == Decimal("90.000000")
    assert eq.equiv_ves_bcv == Decimal("3600.000000")


def test_equivalentes_usd() -> None:
    eq = calcular_equivalentes(Decimal("100"), Moneda.USD, Decimal("36"),
                               Decimal("40"))
    assert eq.equiv_usd_bcv == Decimal("100.000000")
    assert eq.equiv_ves_bcv == Decimal("3600.000000")
    assert eq.equiv_ves_binance == Decimal("4000.000000")


def test_equivalentes_tasa_invalida() -> None:
    with pytest.raises(ValueError):
        calcular_equivalentes(Decimal("100"), Moneda.VES, Decimal("0"), Decimal("40"))


def test_congelar_es_idempotente() -> None:
    v = b.vinculacion(moneda_abono=Moneda.VES, tipo_tasa_abono=TipoTasa.BCV,
                      monto_aplicado="3600", tasa_bcv="36", tasa_binance="40")
    congelar_en_vinculacion(v)
    primero = v.equiv_usd_bcv
    v.tasa_bcv_aplicada = Decimal("99")  # cambiar tasa no debe recalcular
    congelar_en_vinculacion(v)
    assert v.equiv_usd_bcv == primero


def test_ruta_bcv_pura_y_valor_pagado() -> None:
    v1 = b.vinculacion("V1", moneda_abono=Moneda.VES, tipo_tasa_abono=TipoTasa.BCV,
                       monto_aplicado="3600", tasa_bcv="36", tasa_binance="40")
    congelar_en_vinculacion(v1)
    assert es_ruta_bcv_pura([v1]) is True
    assert es_ruta_bcv_pura([]) is False
    assert valor_pagado_usd([v1]) == Decimal("100.000000")


def test_ruta_no_pura_con_abono_binance() -> None:
    v = b.vinculacion(moneda_abono=Moneda.VES, tipo_tasa_abono=TipoTasa.BINANCE,
                      monto_aplicado="4000", tasa_bcv="36", tasa_binance="40")
    assert es_ruta_bcv_pura([v]) is False


def test_valor_pagado_binance_route() -> None:
    v = b.vinculacion(moneda_abono=Moneda.VES, tipo_tasa_abono=TipoTasa.BINANCE,
                      monto_aplicado="4000", tasa_bcv="36", tasa_binance="40")
    congelar_en_vinculacion(v)
    assert valor_pagado_usd([v]) == Decimal("100.000000")


def test_valor_pagado_ruta_usd_directo() -> None:
    # tipo_tasa_abono N_A (USD directo) usa el equivalente USD-binance congelado.
    v = b.vinculacion(moneda_abono=Moneda.USD, tipo_tasa_abono=TipoTasa.N_A,
                      monto_aplicado="100", tasa_bcv="36", tasa_binance="40")
    congelar_en_vinculacion(v)
    assert valor_pagado_usd([v]) == Decimal("100.000000")


def test_valor_pagado_sin_congelar_falla() -> None:
    v = b.vinculacion(moneda_abono=Moneda.VES, tipo_tasa_abono=TipoTasa.BCV)
    with pytest.raises(ValueError, match="congelar"):
        valor_pagado_usd([v])


# --- reconcile (clasificar_diferencia) --------------------------------------
RECON = ReconciliationConfig(
    tolerance_rounding=Decimal("0.01"), tolerance_red=Decimal("1.00")
)


def test_clasificar_verde_dentro_de_redondeo() -> None:
    # neto Odoo = 100.00 - 0 ; dif = 0.01 <= tolerancia_redondeo → VERDE.
    c = clasificar_diferencia(
        Decimal("100.01"), Decimal("100.00"), Decimal("0"), RECON
    )
    assert c.resultado == ResultadoConciliacion.VERDE
    assert c.diferencia == Decimal("0.01")
    assert c.monto_odoo == Decimal("100.00")
    assert c.ncs_odoo == Decimal("0.00")


def test_clasificar_amarillo_entre_tolerancias() -> None:
    # dif = 0.50 → entre redondeo (0.01) y roja (1.00) → AMARILLO.
    c = clasificar_diferencia(
        Decimal("100.50"), Decimal("100.00"), Decimal("0"), RECON
    )
    assert c.resultado == ResultadoConciliacion.AMARILLO
    assert c.diferencia == Decimal("0.50")


def test_clasificar_rojo_supera_tolerancia_roja() -> None:
    # dif = 5.00 > tolerancia roja (1.00) → ROJO.
    c = clasificar_diferencia(
        Decimal("105.00"), Decimal("100.00"), Decimal("0"), RECON
    )
    assert c.resultado == ResultadoConciliacion.ROJO
    assert c.diferencia == Decimal("5.00")


def test_clasificar_resta_ncs_del_neto_odoo() -> None:
    # neto Odoo = 110 - 10 = 100; total_motor 100 → VERDE pese a monto bruto 110.
    c = clasificar_diferencia(
        Decimal("100.00"), Decimal("110.00"), Decimal("10.00"), RECON
    )
    assert c.resultado == ResultadoConciliacion.VERDE
    assert c.diferencia == Decimal("0.00")
    assert c.total_motor == Decimal("100.00")
    assert c.ncs_odoo == Decimal("10.00")
    assert c.so_id == ""
