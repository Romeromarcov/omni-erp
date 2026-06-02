"""Ola 5.2 — Tests del motor de cálculo de nómina LOTTT (puro, sin BD)."""
from decimal import Decimal

from apps.nomina.calculo_lottt import (
    EntradaNomina,
    ParametrosLOTTT,
    calcular_islr,
    calcular_nomina,
    salario_diario,
    valor_hora,
)

P = ParametrosLOTTT()  # defaults VE


def D(x):
    return Decimal(str(x))


def test_salario_diario_y_valor_hora():
    assert salario_diario(D("3000"), P) == D("100")
    assert valor_hora(D("3000"), P) == D("3000") / D("180")


def test_salario_periodo_mes_completo():
    r = calcular_nomina(EntradaNomina(salario_mensual=D("3000"), dias_trabajados=30), P)
    assert r.salario_periodo == D("3000.00")


def test_salario_periodo_parcial():
    r = calcular_nomina(EntradaNomina(salario_mensual=D("3000"), dias_trabajados=15), P)
    assert r.salario_periodo == D("1500.00")


def test_horas_extra_diurnas_recargo_50():
    r = calcular_nomina(
        EntradaNomina(salario_mensual=D("3000"), horas_extra_diurnas=D("10")), P
    )
    # 3000/180 * 1.5 * 10 = 250.00
    assert r.monto_horas_extra_diurnas == D("250.00")


def test_horas_extra_nocturnas_recargo_100():
    r = calcular_nomina(
        EntradaNomina(salario_mensual=D("3000"), horas_extra_nocturnas=D("10")), P
    )
    # 3000/180 * 2 * 10 = 333.33
    assert r.monto_horas_extra_nocturnas == D("333.33")


def test_bono_nocturno_recargo_30():
    r = calcular_nomina(
        EntradaNomina(salario_mensual=D("3000"), horas_nocturnas=D("8")), P
    )
    # 3000/180 * 0.30 * 8 = 40.00
    assert r.monto_bono_nocturno == D("40.00")


def test_deducciones_sso_faov_rpe():
    r = calcular_nomina(EntradaNomina(salario_mensual=D("3000")), P)
    assert r.sso == D("120.00")   # 4%
    assert r.faov == D("30.00")   # 1%
    assert r.rpe == D("15.00")    # 0.5%
    assert r.islr == D("0")       # aplica_islr=False por defecto
    assert r.total_deducciones == D("165.00")


def test_neto_pagar():
    r = calcular_nomina(EntradaNomina(salario_mensual=D("3000")), P)
    assert r.neto_pagar == D("2835.00")  # 3000 - 165


def test_cestaticket_suma_al_neto_pero_no_a_la_base_de_deduccion():
    r = calcular_nomina(
        EntradaNomina(salario_mensual=D("3000"), cestaticket_mensual=D("500")), P
    )
    # deducciones sobre 3000 (no sobre 3500)
    assert r.total_deducciones == D("165.00")
    assert r.cestaticket == D("500.00")
    assert r.neto_pagar == D("3335.00")  # 3000 + 500 - 165


def test_provisiones_mes_completo_sin_antiguedad():
    r = calcular_nomina(EntradaNomina(salario_mensual=D("3000")), P)
    assert r.provision_utilidades == D("250.00")       # 100 * 30 / 12
    assert r.provision_vacaciones == D("125.00")       # 100 * 15 / 12
    assert r.provision_bono_vacacional == D("125.00")  # 100 * 15 / 12
    assert r.provision_prestaciones == D("500.00")     # 100 * (15/3)


def test_provisiones_con_antiguedad():
    r = calcular_nomina(
        EntradaNomina(salario_mensual=D("3000"), antiguedad_anios=5), P
    )
    # vacaciones: 15 + min(5*1, 15) = 20 días → 100*20/12 = 166.67
    assert r.provision_vacaciones == D("166.67")
    # prestaciones: 5 días/mes + (5-1)*2/12 = 5 + 0.6667 → 100*5.6667 = 566.67
    assert r.provision_prestaciones == D("566.67")


def test_dias_adicionales_vacaciones_topados():
    r = calcular_nomina(
        EntradaNomina(salario_mensual=D("3000"), antiguedad_anios=50), P
    )
    # 15 + min(50, 15) = 30 días → 100*30/12 = 250.00
    assert r.provision_vacaciones == D("250.00")


def test_aportes_patronales():
    r = calcular_nomina(EntradaNomina(salario_mensual=D("3000")), P)
    assert r.aporte_patronal_sso == D("270.00")    # 9%
    assert r.aporte_patronal_faov == D("60.00")    # 2%
    assert r.aporte_patronal_inces == D("60.00")   # 2%
    assert r.aporte_patronal_rpe == D("60.00")     # 2%
    assert r.total_aportes_patronales == D("450.00")


def test_islr_off_por_defecto():
    assert calcular_islr(D("10000"), P) == D("0")


def test_islr_progresivo_primer_tramo():
    params = ParametrosLOTTT(aplica_islr=True, valor_ut=D("9.00"))
    # base 600/mes → anual 7200 → /9 = 800 UT (tramo 0-1000, 6%, sustraendo 0)
    # 800*0.06 = 48 UT * 9 = 432 / 12 = 36.00
    assert calcular_islr(D("600"), params) == D("36.00")


def test_resultado_as_dict_serializable():
    r = calcular_nomina(EntradaNomina(salario_mensual=D("3000")), P)
    d = r.as_dict()
    assert d["neto_pagar"] == D("2835.00")
    assert all(isinstance(v, Decimal) for v in d.values())
