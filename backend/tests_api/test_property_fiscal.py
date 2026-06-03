"""
TEST-3 — Tests property-based (hypothesis) de invariantes de dinero (fiscal).

Ejercitan `calcular_iva` y `calcular_igtf` (funciones puras, sin BD, con empresa=None)
sobre miles de entradas generadas, verificando invariantes que deben cumplirse SIEMPRE:
sumas exactas, no-negatividad, redondeo a 2 decimales y reglas de aplicabilidad del IGTF.

Complementa los tests por-ejemplo existentes: hypothesis encuentra los casos borde
(montos enormes, redondeos límite) que un test fijo no cubre.
"""

from decimal import ROUND_HALF_UP, Decimal

import pytest

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.fiscal.services import (
    METODOS_PAGO_IGTF,
    TASA_IGTF_DEFAULT,
    TASA_IVA_EXENTO,
    TASA_IVA_GENERAL,
    TASA_IVA_REDUCIDO,
    ImpuestoError,
    calcular_igtf,
    calcular_iva,
)

pytestmark = pytest.mark.unit

# Montos monetarios no negativos, hasta mil millones, 2 decimales.
montos = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000000000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

TASAS_IVA = {"GENERAL": TASA_IVA_GENERAL, "REDUCIDO": TASA_IVA_REDUCIDO, "EXENTO": TASA_IVA_EXENTO}
METODOS_NO_IGTF = ["EFECTIVO_BS", "TRANSFERENCIA_BS", "PAGO_MOVIL", "TARJETA_DEBITO"]


def _q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── IVA ──────────────────────────────────────────────────────────────────────

@settings(max_examples=300)
@given(subtotal=montos, tipo_iva=st.sampled_from(list(TASAS_IVA)))
def test_iva_invariantes(subtotal, tipo_iva):
    r = calcular_iva(subtotal, tipo_iva, empresa=None)
    tasa = TASAS_IVA[tipo_iva]

    # Suma exacta: total == base + iva
    assert r["total"] == r["base_imponible"] + r["monto_iva"]
    # La base es el subtotal de entrada
    assert r["base_imponible"] == subtotal
    # IVA = redondeo a 2 decimales de subtotal*tasa
    assert r["monto_iva"] == _q2(subtotal * tasa)
    # Nunca negativo
    assert r["monto_iva"] >= 0
    # Redondeado a 2 decimales (exponente >= -2)
    assert -r["monto_iva"].as_tuple().exponent <= 2


@settings(max_examples=100)
@given(subtotal=montos)
def test_iva_exento_es_cero(subtotal):
    r = calcular_iva(subtotal, "EXENTO", empresa=None)
    assert r["monto_iva"] == 0
    assert r["total"] == subtotal


@settings(max_examples=100)
@given(subtotal=st.decimals(min_value=Decimal("-1000000"), max_value=Decimal("-0.01"), places=2))
def test_iva_subtotal_negativo_falla(subtotal):
    with pytest.raises(ImpuestoError):
        calcular_iva(subtotal, "GENERAL", empresa=None)


# ── IGTF ─────────────────────────────────────────────────────────────────────

@settings(max_examples=300)
@given(monto=montos, metodo=st.sampled_from(sorted(METODOS_PAGO_IGTF)))
def test_igtf_aplica_invariantes(monto, metodo):
    r = calcular_igtf(monto, metodo, empresa=None)
    assert r["aplica"] is True
    assert r["tasa"] == TASA_IGTF_DEFAULT
    assert r["monto_igtf"] == _q2(monto * TASA_IGTF_DEFAULT)
    assert r["monto_igtf"] >= 0
    assert r["base"] == monto
    # Suma exacta
    assert r["total_con_igtf"] == r["base"] + r["monto_igtf"]


@settings(max_examples=200)
@given(monto=montos, metodo=st.sampled_from(METODOS_NO_IGTF))
def test_igtf_no_aplica_a_metodos_en_bolivares(monto, metodo):
    r = calcular_igtf(monto, metodo, empresa=None)
    assert r["aplica"] is False
    assert r["monto_igtf"] == 0
    assert r["total_con_igtf"] == monto
