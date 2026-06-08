"""
Unit de la **orquestación** de nómina (`apps.nomina.services`) — la capa que el plan
"Cero Dudas" marcó como hueco: el núcleo puro `calculo_lottt` estaba testeado, pero el
mapeo ORM→motor (Ola 5.2) estaba a 0% de cobertura.

No necesita BD: las funciones usan ``getattr`` (duck-typing) sobre empleado/período, así
que se ejercitan con stubs ligeros (``SimpleNamespace``). Verifica la lectura defensiva
del salario, el cálculo de antigüedad y que la orquestación end-to-end devuelve un
``ResultadoNomina`` coherente (Decimal, neto = asignaciones − deducciones).
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.nomina.calculo_lottt import EntradaNomina, ResultadoNomina
from apps.nomina.services import (
    _antiguedad_anios,
    _salario_mensual,
    calcular_nomina_empleado,
    entrada_desde_empleado,
)

pytestmark = pytest.mark.unit


# ── _salario_mensual: lectura defensiva por orden de preferencia ────────────────


def test_salario_usa_salario_mensual_primero():
    emp = SimpleNamespace(salario_mensual=1500, sueldo_base=999)
    assert _salario_mensual(emp) == Decimal("1500")


@pytest.mark.parametrize(
    "attr, valor",
    [("sueldo_base", 1200), ("salario_base", 1100), ("salario", 1000)],
)
def test_salario_cae_a_alternativas(attr, valor):
    emp = SimpleNamespace(**{attr: valor})
    assert _salario_mensual(emp) == Decimal(str(valor))


def test_salario_sin_ningun_campo_es_cero():
    assert _salario_mensual(SimpleNamespace()) == Decimal("0")


def test_salario_devuelve_decimal_desde_float():
    emp = SimpleNamespace(salario_mensual=1234.56)
    res = _salario_mensual(emp)
    assert isinstance(res, Decimal)
    assert res == Decimal("1234.56")


# ── _antiguedad_anios ───────────────────────────────────────────────────────────


def test_antiguedad_usa_fecha_fin():
    emp = SimpleNamespace(fecha_ingreso=date(2020, 1, 1))
    periodo = SimpleNamespace(fecha_fin=date(2026, 1, 1))
    # 6 años exactos (≈2192 días // 365 = 6)
    assert _antiguedad_anios(emp, periodo) == 6


def test_antiguedad_cae_a_fecha_pago_si_no_hay_fecha_fin():
    emp = SimpleNamespace(fecha_ingreso=date(2023, 1, 1))
    periodo = SimpleNamespace(fecha_pago=date(2026, 1, 1))
    assert _antiguedad_anios(emp, periodo) == 3


def test_antiguedad_cero_si_falta_fecha_ingreso():
    periodo = SimpleNamespace(fecha_fin=date(2026, 1, 1))
    assert _antiguedad_anios(SimpleNamespace(), periodo) == 0


def test_antiguedad_cero_si_falta_fecha_corte():
    emp = SimpleNamespace(fecha_ingreso=date(2020, 1, 1))
    assert _antiguedad_anios(emp, SimpleNamespace()) == 0


def test_antiguedad_no_negativa_si_ingreso_futuro():
    emp = SimpleNamespace(fecha_ingreso=date(2030, 1, 1))
    periodo = SimpleNamespace(fecha_fin=date(2026, 1, 1))
    assert _antiguedad_anios(emp, periodo) == 0


# ── entrada_desde_empleado ──────────────────────────────────────────────────────


def test_entrada_desde_empleado_arma_entradanomina():
    emp = SimpleNamespace(salario_mensual=3000, fecha_ingreso=date(2021, 1, 1))
    periodo = SimpleNamespace(fecha_fin=date(2026, 1, 1))
    entrada = entrada_desde_empleado(
        emp,
        periodo,
        dias_trabajados=15,
        horas_extra_diurnas=Decimal("4"),
        cestaticket_mensual=Decimal("100"),
    )
    assert isinstance(entrada, EntradaNomina)
    assert entrada.salario_mensual == Decimal("3000")
    assert entrada.dias_trabajados == 15
    assert entrada.horas_extra_diurnas == Decimal("4")
    assert entrada.cestaticket_mensual == Decimal("100")
    assert entrada.antiguedad_anios == 5  # 2021→2026


def test_entrada_usa_defaults_cuando_no_se_pasan_kwargs():
    emp = SimpleNamespace(salario_mensual=2000)
    periodo = SimpleNamespace()
    entrada = entrada_desde_empleado(emp, periodo)
    assert entrada.dias_trabajados == 30
    assert entrada.horas_extra_diurnas == Decimal("0")
    assert entrada.antiguedad_anios == 0


# ── calcular_nomina_empleado: orquestación end-to-end ───────────────────────────


def test_calcular_nomina_empleado_devuelve_resultado_coherente():
    emp = SimpleNamespace(salario_mensual=Decimal("3000"), fecha_ingreso=date(2022, 1, 1))
    periodo = SimpleNamespace(fecha_fin=date(2026, 1, 1))
    res = calcular_nomina_empleado(emp, periodo, dias_trabajados=30)

    assert isinstance(res, ResultadoNomina)
    # Invariante contable básica del período: neto = asignaciones − deducciones.
    assert res.neto_pagar == res.total_asignaciones - res.total_deducciones
    # Con salario positivo hay devengado y deducciones legales (>0).
    assert res.total_asignaciones > 0
    assert res.total_deducciones > 0
    assert res.neto_pagar > 0


def test_calcular_nomina_empleado_salario_cero_neto_cero():
    emp = SimpleNamespace()  # sin salario → 0
    periodo = SimpleNamespace()
    res = calcular_nomina_empleado(emp, periodo)
    assert res.total_deducciones == Decimal("0.00")
    assert res.neto_pagar == Decimal("0.00")
