"""
Unit puro (sin BD) del algoritmo de generación de cuotas de acuerdos de pago CxC
(``apps.cxc.services.cuotas``). La función no tiene I/O: recibe el ``acuerdo`` como
FK opaca y devuelve dicts para ``bulk_create``, así que se prueba con un centinela.

Invariante de dinero central: **la suma de las cuotas == monto_total** (la última
cuota absorbe el ajuste de redondeo), sin cuotas negativas y con fechas correctas
según periodicidad (incluido el manejo de fin de mes).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.cxc.services.cuotas import _proxima_fecha, generar_cuotas

pytestmark = pytest.mark.unit

_ACUERDO = object()  # centinela: la función solo lo reempaqueta


def _suma(cuotas):
    return sum((c["monto"] for c in cuotas), Decimal("0"))


# ── _proxima_fecha ──────────────────────────────────────────────────────────────


def test_proxima_fecha_semanal():
    assert _proxima_fecha(date(2026, 1, 1), "semanal", 2) == date(2026, 1, 15)


def test_proxima_fecha_quincenal():
    assert _proxima_fecha(date(2026, 1, 1), "quincenal", 2) == date(2026, 1, 31)


def test_proxima_fecha_mensual_simple():
    assert _proxima_fecha(date(2026, 1, 15), "mensual", 2) == date(2026, 3, 15)


def test_proxima_fecha_mensual_fin_de_mes():
    # 31 ene + 1 mes → 28 feb (2026 no bisiesto): no desborda a marzo.
    assert _proxima_fecha(date(2026, 1, 31), "mensual", 1) == date(2026, 2, 28)


def test_proxima_fecha_mensual_cruza_anio():
    assert _proxima_fecha(date(2026, 11, 30), "mensual", 2) == date(2027, 1, 30)


def test_proxima_fecha_unico_devuelve_base():
    assert _proxima_fecha(date(2026, 5, 10), "unico", 3) == date(2026, 5, 10)


# ── generar_cuotas: pago único ──────────────────────────────────────────────────


def test_unico_una_sola_cuota_por_el_total():
    cuotas = generar_cuotas(_ACUERDO, date(2026, 1, 1), 90, "unico", Decimal("100.00"))
    assert len(cuotas) == 1
    assert cuotas[0]["numero_cuota"] == 1
    assert cuotas[0]["fecha_vencimiento"] == date(2026, 1, 1)
    assert cuotas[0]["monto"] == Decimal("100.00")
    assert cuotas[0]["estado"] == "pendiente"


# ── generar_cuotas: división equitativa (ajuste en la última) ───────────────────


def test_division_equitativa_suma_exacta():
    # 100 / 3 = 33.33 ; última = 100 - 66.66 = 33.34
    cuotas = generar_cuotas(_ACUERDO, date(2026, 1, 1), 90, "mensual", Decimal("100.00"))
    assert len(cuotas) == 3
    assert [c["monto"] for c in cuotas] == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    assert _suma(cuotas) == Decimal("100.00")
    assert [c["numero_cuota"] for c in cuotas] == [1, 2, 3]


def test_numero_de_cuotas_por_periodicidad():
    # semanal: 28 días // 7 = 4 cuotas
    cuotas = generar_cuotas(_ACUERDO, date(2026, 1, 1), 28, "semanal", Decimal("400.00"))
    assert len(cuotas) == 4
    assert _suma(cuotas) == Decimal("400.00")
    # fechas semanales
    assert cuotas[1]["fecha_vencimiento"] == date(2026, 1, 8)


def test_plazo_menor_que_periodo_da_una_cuota():
    # 5 días // 30 = 0 → max(1, 0) = 1 cuota
    cuotas = generar_cuotas(_ACUERDO, date(2026, 1, 1), 5, "mensual", Decimal("50.00"))
    assert len(cuotas) == 1
    assert _suma(cuotas) == Decimal("50.00")


# ── generar_cuotas: monto fijo por cuota ────────────────────────────────────────


def test_monto_cuota_fijo_ajusta_ultima():
    # total 100, monto_cuota 40, mensual, plazo 90 → 3 cuotas: 40,40, última=20
    cuotas = generar_cuotas(
        _ACUERDO, date(2026, 1, 1), 90, "mensual", Decimal("100.00"),
        monto_cuota=Decimal("40.00"),
    )
    assert [c["monto"] for c in cuotas] == [Decimal("40.00"), Decimal("40.00"), Decimal("20.00")]
    assert _suma(cuotas) == Decimal("100.00")


# ── generar_cuotas: porcentaje de abono ─────────────────────────────────────────


def test_porcentaje_abono():
    # total 1000, 25% → 250 por cuota, plazo 120 mensual → 4 cuotas de 250
    cuotas = generar_cuotas(
        _ACUERDO, date(2026, 1, 1), 120, "mensual", Decimal("1000.00"),
        porcentaje_abono=Decimal("25"),
    )
    assert len(cuotas) == 4
    assert all(c["monto"] == Decimal("250.00") for c in cuotas)
    assert _suma(cuotas) == Decimal("1000.00")


# ── generar_cuotas: no genera cuotas negativas ──────────────────────────────────


def test_no_genera_cuotas_negativas_por_monto_fijo_alto():
    # monto_cuota 60 con total 100, mensual plazo 90 → num=3.
    # i=1,2 usan 60 (60,60); la última sería 100-120 = -20 → se OMITE
    # (la guarda `monto_esta <= 0: continue`). Resultado: 2 cuotas, sin negativos.
    cuotas = generar_cuotas(
        _ACUERDO, date(2026, 1, 1), 90, "mensual", Decimal("100.00"),
        monto_cuota=Decimal("60.00"),
    )
    assert all(c["monto"] > 0 for c in cuotas)
    assert [c["monto"] for c in cuotas] == [Decimal("60.00"), Decimal("60.00")]


def test_quincenal_numero_y_fechas():
    # 45 días // 15 = 3 cuotas quincenales (cubre la rama quincenal de num_cuotas).
    cuotas = generar_cuotas(_ACUERDO, date(2026, 1, 1), 45, "quincenal", Decimal("300.00"))
    assert len(cuotas) == 3
    assert _suma(cuotas) == Decimal("300.00")
    assert cuotas[1]["fecha_vencimiento"] == date(2026, 1, 16)  # +15 días
