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


# ── Ramas de ISLR no cubiertas (runner de mutación) ──────────────────────────


def test_islr_base_cero_o_negativa_devuelve_cero():
    params = ParametrosLOTTT(aplica_islr=True)
    assert calcular_islr(D("0"), params) == D("0")
    assert calcular_islr(D("-100"), params) == D("0")


def test_islr_tramo_medio_12pct():
    params = ParametrosLOTTT(aplica_islr=True, valor_ut=D("9.00"))
    # base 1200/mes → anual 14400 → /9 = 1600 UT (tramo 1500–2000, 12%, sustraendo 75)
    # 1600*0.12 − 75 = 117 UT → *9 = 1053 → /12 = 87.75
    assert calcular_islr(D("1200"), params) == D("87.75")


def test_islr_tramo_superior_sin_tope():
    params = ParametrosLOTTT(aplica_islr=True, valor_ut=D("9.00"))
    # base 5000/mes → anual 60000 → /9 ≈ 6666.67 UT (tramo 6000+, 34%, sustraendo 875)
    # 60000*0.34 = 20400 − 875*9 = 7875 → 12525 → /12 = 1043.75
    assert calcular_islr(D("5000"), params) == D("1043.75")


def test_islr_impuesto_negativo_se_trunca_a_cero():
    """Tramo artificial con sustraendo mayor que el impuesto → 0 (rama <= 0)."""
    from apps.nomina.calculo_lottt import TramoISLR

    tramos = (TramoISLR(D("0"), None, D("0.06"), D("100")),)
    params = ParametrosLOTTT(aplica_islr=True, valor_ut=D("9.00"), tramos_islr=tramos)
    # base 600/mes → 800 UT → 48 − 100 = −52 → 0
    assert calcular_islr(D("600"), params) == D("0")


def test_islr_se_incluye_en_total_deducciones():
    params = ParametrosLOTTT(aplica_islr=True, valor_ut=D("9.00"))
    r = calcular_nomina(EntradaNomina(salario_mensual=D("3000")), params)
    # base 3000 → anual 36000 → 4000 UT exactas (tramo 2000–2500? no: 4000 está
    # en el borde del tramo 3000–4000, 24%, sustraendo 375):
    # 4000*0.24 − 375 = 585 UT → *9 = 5265 → /12 = 438.75
    assert r.islr == D("438.75")
    # total = sso 120 + faov 30 + rpe 15 + islr 438.75 = 603.75
    assert r.total_deducciones == D("603.75")
    assert r.neto_pagar == D("2396.25")  # 3000 − 603.75


# ── Otras asignaciones / deducciones ─────────────────────────────────────────


def test_otras_asignaciones_engordan_base_salarial():
    r = calcular_nomina(
        EntradaNomina(salario_mensual=D("3000"), otras_asignaciones=D("200")), P
    )
    assert r.otras_asignaciones == D("200.00")
    assert r.total_devengado_salarial == D("3200.00")
    # las deducciones se calculan sobre 3200: sso 128, faov 32, rpe 16
    assert r.sso == D("128.00")
    assert r.faov == D("32.00")
    assert r.rpe == D("16.00")
    assert r.neto_pagar == D("3024.00")  # 3200 − 176


def test_otras_deducciones_restan_del_neto():
    r = calcular_nomina(
        EntradaNomina(salario_mensual=D("3000"), otras_deducciones=D("100")), P
    )
    assert r.otras_deducciones == D("100.00")
    assert r.total_deducciones == D("265.00")  # 165 + 100
    assert r.neto_pagar == D("2735.00")


def test_total_asignaciones_es_salarial_mas_cestaticket():
    r = calcular_nomina(
        EntradaNomina(salario_mensual=D("3000"), cestaticket_mensual=D("400")), P
    )
    assert r.total_asignaciones == D("3400.00")


def test_combinado_todos_los_conceptos():
    """Caso integral: cada término con valor exacto (mata mutantes de suma)."""
    r = calcular_nomina(
        EntradaNomina(
            salario_mensual=D("3600"),
            dias_trabajados=30,
            horas_extra_diurnas=D("6"),    # 3600/180=20 → 6*20*1.5 = 180
            horas_extra_nocturnas=D("3"),  # 3*20*2 = 120
            horas_nocturnas=D("10"),       # 10*20*0.30 = 60
            otras_asignaciones=D("40"),
            cestaticket_mensual=D("500"),
            otras_deducciones=D("25"),
        ),
        P,
    )
    assert r.salario_periodo == D("3600.00")
    assert r.monto_horas_extra_diurnas == D("180.00")
    assert r.monto_horas_extra_nocturnas == D("120.00")
    assert r.monto_bono_nocturno == D("60.00")
    assert r.total_devengado_salarial == D("4000.00")  # 3600+180+120+60+40
    assert r.sso == D("160.00")      # 4% de 4000
    assert r.faov == D("40.00")      # 1%
    assert r.rpe == D("20.00")       # 0.5%
    assert r.total_deducciones == D("245.00")  # 220 + 25
    assert r.total_asignaciones == D("4500.00")  # 4000 + 500
    assert r.neto_pagar == D("4255.00")  # 4500 − 245
    assert r.aporte_patronal_sso == D("360.00")     # 9%
    assert r.total_aportes_patronales == D("600.00")  # 15% de 4000
