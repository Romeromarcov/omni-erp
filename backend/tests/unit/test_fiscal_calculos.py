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


# ── Constantes SENIAT: fijadas con LITERALES ────────────────────────────────────
# (comparar contra la constante importada no mata mutantes de la constante misma)


def test_constantes_seniat_valores_literales():
    from apps.fiscal.services import METODOS_PAGO_IGTF

    assert TASA_IVA_GENERAL == Decimal("0.16")
    assert TASA_IVA_REDUCIDO == Decimal("0.08")
    assert TASA_IVA_EXENTO == Decimal("0")
    assert TASA_IGTF_DEFAULT == Decimal("0.03")
    assert METODOS_PAGO_IGTF == frozenset(
        {"DIVISA_EFECTIVO", "DIVISA_TRANSFERENCIA", "CRYPTO", "PETRO"}
    )


def test_iva_negativo_mensaje_exacto():
    with pytest.raises(ImpuestoError, match="El subtotal no puede ser negativo."):
        calcular_iva(Decimal("-0.01"), "GENERAL")


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


# ── Ramas con `empresa` (mocks de los modelos — sigue siendo unit, sin BD) ──────

from types import SimpleNamespace
from unittest import mock

from apps.fiscal.services import calcular_impuestos


def _empresa_ve(**kwargs):
    base = {"localizacion_legal_activa": True, "pais_codigo_iso": "VE"}
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_iva_con_tasa_configurada_por_empresa():
    from apps.fiscal.models import TasaIVAEmpresa

    with mock.patch.object(
        TasaIVAEmpresa.objects, "get", return_value=SimpleNamespace(tasa="0.10")
    ):
        r = calcular_iva(Decimal("100"), "GENERAL", empresa=_empresa_ve())
    assert r["tasa"] == Decimal("0.10")
    assert r["monto_iva"] == Decimal("10.00")
    assert r["total"] == Decimal("110.00")


def test_iva_empresa_sin_config_usa_default_por_tipo():
    from apps.fiscal.models import TasaIVAEmpresa

    with mock.patch.object(
        TasaIVAEmpresa.objects, "get", side_effect=TasaIVAEmpresa.DoesNotExist
    ):
        assert calcular_iva(Decimal("100"), "GENERAL", empresa=_empresa_ve())["tasa"] == TASA_IVA_GENERAL
        assert calcular_iva(Decimal("100"), "REDUCIDO", empresa=_empresa_ve())["tasa"] == TASA_IVA_REDUCIDO
        assert calcular_iva(Decimal("100"), "EXENTO", empresa=_empresa_ve())["tasa"] == TASA_IVA_EXENTO
        # tipo desconocido cae a GENERAL también en la rama con empresa
        assert calcular_iva(Decimal("100"), "RARO", empresa=_empresa_ve())["tasa"] == TASA_IVA_GENERAL


def test_igtf_empresa_sin_localizacion_legal_no_aplica():
    r = calcular_igtf(
        Decimal("100"), "DIVISA_EFECTIVO", empresa=_empresa_ve(localizacion_legal_activa=False)
    )
    assert r["aplica"] is False
    assert r["monto_igtf"] == Decimal("0")
    assert r["total_con_igtf"] == Decimal("100")


def test_igtf_empresa_pais_no_venezuela_no_aplica():
    r = calcular_igtf(Decimal("100"), "DIVISA_EFECTIVO", empresa=_empresa_ve(pais_codigo_iso="CO"))
    assert r["aplica"] is False


@pytest.mark.parametrize("pais", ["VE", "ve", "VEN", "ven"])
def test_igtf_empresa_venezuela_aplica_case_insensitive(pais):
    from apps.fiscal.models import ConfiguracionFiscalEmpresa

    with mock.patch.object(
        ConfiguracionFiscalEmpresa.objects, "get",
        side_effect=ConfiguracionFiscalEmpresa.DoesNotExist,
    ):
        r = calcular_igtf(Decimal("100"), "DIVISA_EFECTIVO", empresa=_empresa_ve(pais_codigo_iso=pais))
    assert r["aplica"] is True
    assert r["tasa"] == TASA_IGTF_DEFAULT
    assert r["monto_igtf"] == Decimal("3.00")


def test_igtf_empresa_pais_none_aplica():
    """Sin país configurado, la rama del país no desactiva el IGTF."""
    from apps.fiscal.models import ConfiguracionFiscalEmpresa

    with mock.patch.object(
        ConfiguracionFiscalEmpresa.objects, "get",
        side_effect=ConfiguracionFiscalEmpresa.DoesNotExist,
    ):
        r = calcular_igtf(Decimal("100"), "CRYPTO", empresa=_empresa_ve(pais_codigo_iso=None))
    assert r["aplica"] is True


def test_igtf_tasa_configurada_por_empresa():
    from apps.fiscal.models import ConfiguracionFiscalEmpresa

    with mock.patch.object(
        ConfiguracionFiscalEmpresa.objects, "get",
        return_value=SimpleNamespace(tasa_igtf="0.02"),
    ):
        r = calcular_igtf(Decimal("100"), "DIVISA_EFECTIVO", empresa=_empresa_ve())
    assert r["tasa"] == Decimal("0.02")
    assert r["monto_igtf"] == Decimal("2.00")
    assert r["total_con_igtf"] == Decimal("102.00")


# ── calcular_impuestos (M8, por empresa+moneda) — mocks sin BD ──────────────────


def _patch_fiscal_config(config=None, tasa_general=None):
    """Context managers para ConfiguracionFiscalEmpresa y TasaIVAEmpresa."""
    from apps.fiscal.models import ConfiguracionFiscalEmpresa, TasaIVAEmpresa

    if config is None:
        cfg_patch = mock.patch.object(
            ConfiguracionFiscalEmpresa.objects, "get",
            side_effect=ConfiguracionFiscalEmpresa.DoesNotExist,
        )
    else:
        cfg_patch = mock.patch.object(
            ConfiguracionFiscalEmpresa.objects, "get", return_value=config
        )

    def _tasa_get(**kwargs):
        if kwargs.get("tipo") == "GENERAL" and tasa_general is not None:
            return SimpleNamespace(tasa=tasa_general)
        raise TasaIVAEmpresa.DoesNotExist

    tasa_patch = mock.patch.object(TasaIVAEmpresa.objects, "get", side_effect=_tasa_get)
    return cfg_patch, tasa_patch


def test_calcular_impuestos_sin_config_defaults():
    """Sin ConfiguracionFiscalEmpresa: IVA 16% (contribuyente) y SIN IGTF."""
    cfg, tasa = _patch_fiscal_config()
    with cfg, tasa:
        r = calcular_impuestos(Decimal("100"), _empresa_ve(), moneda=SimpleNamespace(codigo_iso="USD"))
    assert r["tasa_iva"] == TASA_IVA_GENERAL
    assert r["monto_iva"] == Decimal("16.00")
    assert r["tasa_igtf"] == Decimal("0")
    assert r["monto_igtf"] == Decimal("0")
    assert r["total"] == Decimal("116.00")


def test_calcular_impuestos_no_contribuyente_iva_exento():
    cfg, tasa = _patch_fiscal_config(
        config=SimpleNamespace(contribuyente_iva=False, aplica_igtf=False, tasa_igtf="0.03")
    )
    with cfg, tasa:
        r = calcular_impuestos(Decimal("100"), _empresa_ve())
    assert r["tasa_iva"] == TASA_IVA_EXENTO
    assert r["monto_iva"] == Decimal("0.00")
    assert r["total"] == Decimal("100.00")


def test_calcular_impuestos_igtf_en_divisa():
    cfg, tasa = _patch_fiscal_config(
        config=SimpleNamespace(contribuyente_iva=True, aplica_igtf=True, tasa_igtf="0.03")
    )
    with cfg, tasa:
        r = calcular_impuestos(
            Decimal("100"), _empresa_ve(), moneda=SimpleNamespace(codigo_iso="USD")
        )
    assert r["tasa_igtf"] == Decimal("0.03")
    assert r["monto_igtf"] == Decimal("3.00")
    assert r["total"] == Decimal("119.00")  # 100 + 16 + 3


@pytest.mark.parametrize("codigo", ["VES", "ves", "BS", "VEF", "VEB"])
def test_calcular_impuestos_sin_igtf_en_bolivares(codigo):
    cfg, tasa = _patch_fiscal_config(
        config=SimpleNamespace(contribuyente_iva=True, aplica_igtf=True, tasa_igtf="0.03")
    )
    with cfg, tasa:
        r = calcular_impuestos(
            Decimal("100"), _empresa_ve(), moneda=SimpleNamespace(codigo_iso=codigo)
        )
    assert r["monto_igtf"] == Decimal("0")
    assert r["total"] == Decimal("116.00")


def test_calcular_impuestos_sin_moneda_no_igtf():
    cfg, tasa = _patch_fiscal_config(
        config=SimpleNamespace(contribuyente_iva=True, aplica_igtf=True, tasa_igtf="0.03")
    )
    with cfg, tasa:
        r = calcular_impuestos(Decimal("100"), _empresa_ve(), moneda=None)
    assert r["monto_igtf"] == Decimal("0")


def test_calcular_impuestos_tasa_iva_configurada():
    cfg, tasa = _patch_fiscal_config(
        config=SimpleNamespace(contribuyente_iva=True, aplica_igtf=False, tasa_igtf="0.03"),
        tasa_general="0.08",
    )
    with cfg, tasa:
        r = calcular_impuestos(Decimal("200"), _empresa_ve())
    assert r["tasa_iva"] == Decimal("0.08")
    assert r["monto_iva"] == Decimal("16.00")
    assert r["base_imponible"] == Decimal("200")
    assert r["total"] == Decimal("216.00")
