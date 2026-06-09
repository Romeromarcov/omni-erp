"""
Unit puro (sin BD, sin hypothesis) de los cálculos fiscales de ``apps.fiscal.services``.

Ejercita por-ejemplo las ramas de ``calcular_iva`` / ``calcular_igtf`` /
``calcular_impuestos_pedido`` con ``empresa=None`` (camino de tasas por defecto, sin
tocar la base de datos). Es rápido (<1 s) a propósito: además de documentar el
contrato exacto, sirve como **runner de mutation testing** (``setup.cfg [mutmut]``) —
matar mutantes requiere aserciones que dependan del valor exacto de cada rama, no
sólo que "no explote". Complementa el property-based de ``test_property_fiscal.py``
(que es exhaustivo pero lento por el volumen de hypothesis).
"""

from decimal import Decimal

import pytest

from apps.fiscal.services import (
    TASA_IGTF_DEFAULT,
    TASA_IVA_EXENTO,
    TASA_IVA_GENERAL,
    TASA_IVA_REDUCIDO,
    ImpuestoError,
    calcular_igtf,
    calcular_impuestos_pedido,
    calcular_iva,
)

pytestmark = pytest.mark.unit


# ── calcular_iva ───────────────────────────────────────────────────────────────


def test_iva_general():
    r = calcular_iva(Decimal("100"), "GENERAL")
    assert r["tasa"] == TASA_IVA_GENERAL
    assert r["base_imponible"] == Decimal("100")
    assert r["monto_iva"] == Decimal("16.00")
    assert r["total"] == Decimal("116.00")


def test_iva_reducido():
    r = calcular_iva(Decimal("100"), "REDUCIDO")
    assert r["tasa"] == TASA_IVA_REDUCIDO
    assert r["monto_iva"] == Decimal("8.00")
    assert r["total"] == Decimal("108.00")


def test_iva_exento_es_cero():
    r = calcular_iva(Decimal("100"), "EXENTO")
    assert r["tasa"] == TASA_IVA_EXENTO
    assert r["monto_iva"] == Decimal("0.00")
    assert r["total"] == Decimal("100.00")


def test_iva_tipo_desconocido_cae_a_general():
    # El default del mapeo es GENERAL (no EXENTO ni error).
    r = calcular_iva(Decimal("50"), "INEXISTENTE")
    assert r["tasa"] == TASA_IVA_GENERAL
    assert r["monto_iva"] == Decimal("8.00")


def test_iva_redondeo_half_up():
    # 33.33 * 0.16 = 5.3328 → 5.33 (ROUND_HALF_UP a 2 decimales).
    assert calcular_iva(Decimal("33.33"), "GENERAL")["monto_iva"] == Decimal("5.33")
    # 31.25 * 0.16 = 5.0000 ; 10.94 * 0.16 = 1.7504 → 1.75
    assert calcular_iva(Decimal("10.94"), "GENERAL")["monto_iva"] == Decimal("1.75")
    # 0.16 * 3.125 = 0.50 exacto en frontera .005 → 0.50 (half up)
    assert calcular_iva(Decimal("3.125"), "GENERAL")["monto_iva"] == Decimal("0.50")


def test_iva_cero_subtotal():
    r = calcular_iva(Decimal("0"), "GENERAL")
    assert r["monto_iva"] == Decimal("0.00")
    assert r["total"] == Decimal("0.00")


def test_iva_negativo_levanta_error():
    with pytest.raises(ImpuestoError):
        calcular_iva(Decimal("-1"), "GENERAL")


# ── calcular_igtf ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "metodo", ["DIVISA_EFECTIVO", "DIVISA_TRANSFERENCIA", "CRYPTO", "PETRO"]
)
def test_igtf_aplica_en_metodos_divisa(metodo):
    r = calcular_igtf(Decimal("100"), metodo)
    assert r["aplica"] is True
    assert r["tasa"] == TASA_IGTF_DEFAULT
    assert r["monto_igtf"] == Decimal("3.00")
    assert r["total_con_igtf"] == Decimal("103.00")


@pytest.mark.parametrize("metodo", ["EFECTIVO_BS", "TRANSFERENCIA_BS", "PUNTO_VENTA", ""])
def test_igtf_no_aplica_en_bolivares(metodo):
    r = calcular_igtf(Decimal("100"), metodo)
    assert r["aplica"] is False
    assert r["tasa"] == Decimal("0")
    assert r["monto_igtf"] == Decimal("0")
    assert r["total_con_igtf"] == Decimal("100")


def test_igtf_redondeo():
    # 49.99 * 0.03 = 1.4997 → 1.50
    assert calcular_igtf(Decimal("49.99"), "CRYPTO")["monto_igtf"] == Decimal("1.50")


# ── calcular_impuestos_pedido ───────────────────────────────────────────────────


def test_pedido_mixto_suma_bases_y_ivas():
    lineas = [
        {"subtotal": Decimal("100"), "tipo_iva": "GENERAL"},
        {"subtotal": Decimal("50"), "tipo_iva": "REDUCIDO"},
        {"subtotal": Decimal("30"), "tipo_iva": "EXENTO"},
    ]
    r = calcular_impuestos_pedido(lineas, metodo_pago="EFECTIVO_BS")
    assert r["subtotal"] == Decimal("180")
    assert r["base_general"] == Decimal("100")
    assert r["base_reducida"] == Decimal("50")
    assert r["base_exenta"] == Decimal("30")
    assert r["iva_general"] == Decimal("16.00")
    assert r["iva_reducido"] == Decimal("4.00")
    assert r["total_iva"] == Decimal("20.00")
    # Pago en Bs ⇒ sin IGTF; total = subtotal + IVA.
    assert r["igtf"]["aplica"] is False
    assert r["total"] == Decimal("200.00")


def test_pedido_con_igtf_en_divisa():
    lineas = [{"subtotal": Decimal("100"), "tipo_iva": "GENERAL"}]
    r = calcular_impuestos_pedido(lineas, metodo_pago="DIVISA_EFECTIVO")
    # base 100 + IVA 16 = 116 ; IGTF 3% sobre 116 = 3.48
    assert r["total_iva"] == Decimal("16.00")
    assert r["igtf"]["aplica"] is True
    assert r["igtf"]["monto_igtf"] == Decimal("3.48")
    assert r["total"] == Decimal("119.48")


def test_pedido_vacio():
    r = calcular_impuestos_pedido([], metodo_pago="EFECTIVO_BS")
    assert r["subtotal"] == Decimal("0")
    assert r["total_iva"] == Decimal("0")
    assert r["total"] == Decimal("0")


def test_pedido_tipo_iva_default_general():
    # Sin "tipo_iva" en la línea ⇒ GENERAL.
    r = calcular_impuestos_pedido([{"subtotal": Decimal("100")}], metodo_pago="EFECTIVO_BS")
    assert r["base_general"] == Decimal("100")
    assert r["iva_general"] == Decimal("16.00")
