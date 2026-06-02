"""GAP-2 / ADR-007: framework de localización en dos capas + gating de IGTF."""

from decimal import Decimal

import pytest

from apps.core.models import Empresa
from apps.fiscal.services import calcular_igtf
from apps.localizacion import ports, services


@pytest.mark.django_db
def test_empresa_sin_localizacion_no_aplica_igtf(moneda_usd):
    """Empresa en CO con la capa legal desactivada NO recibe IGTF."""
    empresa_co = Empresa.objects.create(
        nombre_legal="Distribuidora Colombia S.A.S.",
        identificador_fiscal="CO-900123",
        id_moneda_base=moneda_usd,
        pais_codigo_iso="CO",
        localizacion_legal_activa=False,
        localizacion_mercado_activa=False,
    )
    # Divisa efectivo (método sujeto a IGTF en VE) pero empresa no-VE/sin capa legal.
    resultado = calcular_igtf(Decimal("100"), "DIVISA_EFECTIVO", empresa=empresa_co)
    assert resultado["aplica"] is False
    assert resultado["monto_igtf"] == Decimal("0")


@pytest.mark.django_db
def test_empresa_ve_con_localizacion_si_aplica_igtf(moneda_usd):
    """Control: empresa VE con capa legal activa SÍ recibe IGTF (la regla solo apaga, no rompe)."""
    empresa_ve = Empresa.objects.create(
        nombre_legal="Bodega Caracas C.A.", identificador_fiscal="J-555", id_moneda_base=moneda_usd,
        pais_codigo_iso="VE", localizacion_legal_activa=True,
    )
    resultado = calcular_igtf(Decimal("100"), "DIVISA_EFECTIVO", empresa=empresa_ve)
    assert resultado["aplica"] is True
    assert resultado["monto_igtf"] > Decimal("0")


@pytest.mark.django_db
def test_localizacion_resuelve_noop_para_capa_legal_desactivada(moneda_usd):
    empresa_co = Empresa.objects.create(
        nombre_legal="X", identificador_fiscal="CO-1", id_moneda_base=moneda_usd,
        pais_codigo_iso="CO", localizacion_legal_activa=False,
    )
    loc = services.get_localizacion(empresa_co)
    assert isinstance(loc["MotorImpuestos"], ports.MotorImpuestosNoOp)
    impuestos = loc["MotorImpuestos"].calcular(subtotal=Decimal("100"), empresa=empresa_co)
    assert impuestos["total_impuestos"] == Decimal("0")


def test_registry_register_y_get():
    from apps.localizacion import registry

    sentinel = {"MotorImpuestos": object()}
    registry.register("ZZ", sentinel)
    assert registry.get("zz") == sentinel  # case-insensitive
    assert "ZZ" in registry.paises_registrados()
