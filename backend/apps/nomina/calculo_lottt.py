"""Motor de cálculo de nómina venezolana (LOTTT) — núcleo PURO.

Este módulo NO toca la base de datos ni el ORM: recibe primitivas (Decimal, int)
y devuelve resultados Decimal. Es código de cálculo puro (R-CODE-4 Decimal,
§5.2-ter del Plan Maestro: las reglas de dinero/IVA/nómina deben ser puras para
poder vivir en `packages/domain` y ser trivialmente testeables).

Cubre los conceptos documentados en el Plan Maestro §6.2:
  Devengados:   salario del período, horas extra (50% diurnas / 100% nocturnas),
                bono nocturno (recargo), cestaticket / bono de alimentación.
  Deducciones:  SSO (4%), FAOV/RPVH (1%), RPE/paro forzoso (0.5%), ISLR.
  Provisiones:  utilidades, vacaciones + bono vacacional, prestaciones (antigüedad).
  Aportes patronales (informativos): SSO 9%, FAOV 2%, INCES 2%, RPE 2%.

Todas las tasas, días y topes son parámetros (`ParametrosLOTTT`) con defaults
venezolanos, de modo que el motor se adapta cuando cambian las leyes/decretos sin
tocar la lógica. El orquestador (`services.py`) inyecta los valores reales desde
`ParametroSistema` por empresa.

Nota sobre el ISLR: la retención de ISLR sobre sueldos en Venezuela se calcula
formalmente vía el porcentaje ARC (estimación anual). Aquí se ofrece un cálculo
**progresivo por tramos en UT, simplificado y parametrizable** como base; la
fórmula ARC oficial se conecta sustituyendo `calcular_islr` o pasando tramos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

CENTAVO = Decimal("0.01")


def q(valor) -> Decimal:
    """Redondea a 2 decimales (centavos) con HALF_UP."""
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _d(valor) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


@dataclass(frozen=True)
class TramoISLR:
    """Tramo progresivo de ISLR expresado en Unidades Tributarias (UT) anuales."""
    desde_ut: Decimal
    hasta_ut: Decimal | None  # None = sin tope superior
    tasa: Decimal             # ej. Decimal("0.06") = 6%
    sustraendo_ut: Decimal = Decimal("0")


# Tabla progresiva ISLR (Art. 50 LISLR), en UT anuales. Simplificada/parametrizable.
TRAMOS_ISLR_DEFAULT: tuple[TramoISLR, ...] = (
    TramoISLR(Decimal("0"), Decimal("1000"), Decimal("0.06"), Decimal("0")),
    TramoISLR(Decimal("1000"), Decimal("1500"), Decimal("0.09"), Decimal("30")),
    TramoISLR(Decimal("1500"), Decimal("2000"), Decimal("0.12"), Decimal("75")),
    TramoISLR(Decimal("2000"), Decimal("2500"), Decimal("0.16"), Decimal("155")),
    TramoISLR(Decimal("2500"), Decimal("3000"), Decimal("0.20"), Decimal("255")),
    TramoISLR(Decimal("3000"), Decimal("4000"), Decimal("0.24"), Decimal("375")),
    TramoISLR(Decimal("4000"), Decimal("6000"), Decimal("0.29"), Decimal("575")),
    TramoISLR(Decimal("6000"), None, Decimal("0.34"), Decimal("875")),
)


@dataclass(frozen=True)
class ParametrosLOTTT:
    """Parámetros legales/económicos (con defaults venezolanos vigentes)."""
    # ── Deducciones del trabajador ──
    sso_empleado: Decimal = Decimal("0.04")
    faov_empleado: Decimal = Decimal("0.01")
    rpe_empleado: Decimal = Decimal("0.005")
    # ── Aportes patronales (informativos, no se descuentan al trabajador) ──
    sso_patronal: Decimal = Decimal("0.09")
    faov_patronal: Decimal = Decimal("0.02")
    inces_patronal: Decimal = Decimal("0.02")
    rpe_patronal: Decimal = Decimal("0.02")
    # ── Recargos ──
    recargo_hora_extra_diurna: Decimal = Decimal("0.50")    # +50%
    recargo_hora_extra_nocturna: Decimal = Decimal("1.00")  # +100%
    recargo_bono_nocturno: Decimal = Decimal("0.30")        # +30% sobre hora nocturna
    # ── Jornada / base ──
    dias_mes: int = 30
    horas_jornada_mensual: Decimal = Decimal("180")  # 30 días * 6 h (jornada legal diurna)
    # ── Provisiones (días por año) ──
    dias_utilidades_anuales: int = 30           # mínimo legal 15, máx 120
    dias_vacaciones_anuales: int = 15           # base 15 + 1/año (tope 15+15)
    dias_bono_vacacional_anuales: int = 15
    dias_adicionales_vacaciones_por_anio: int = 1
    tope_dias_adicionales_vacaciones: int = 15
    dias_prestaciones_trimestre: int = 15       # garantía LOTTT art. 142(a)
    dias_prestaciones_adicionales_anuales: int = 2  # art. 142(b), tras el 1er año
    # ── ISLR ──
    valor_ut: Decimal = Decimal("9.00")  # Bs por UT (configurable por decreto)
    tramos_islr: tuple[TramoISLR, ...] = TRAMOS_ISLR_DEFAULT
    aplica_islr: bool = False  # solo si el trabajador supera el umbral exento


@dataclass(frozen=True)
class EntradaNomina:
    """Datos de un trabajador para un período de nómina."""
    salario_mensual: Decimal
    dias_trabajados: int = 30
    horas_extra_diurnas: Decimal = Decimal("0")
    horas_extra_nocturnas: Decimal = Decimal("0")
    horas_nocturnas: Decimal = Decimal("0")  # para el bono nocturno
    antiguedad_anios: int = 0
    cestaticket_mensual: Decimal = Decimal("0")  # bono de alimentación (no salarial)
    otras_asignaciones: Decimal = Decimal("0")
    otras_deducciones: Decimal = Decimal("0")


@dataclass
class ResultadoNomina:
    # Devengados salariales
    salario_periodo: Decimal
    monto_horas_extra_diurnas: Decimal
    monto_horas_extra_nocturnas: Decimal
    monto_bono_nocturno: Decimal
    otras_asignaciones: Decimal
    total_devengado_salarial: Decimal  # base para deducciones
    # Asignaciones no salariales
    cestaticket: Decimal
    # Deducciones
    sso: Decimal
    faov: Decimal
    rpe: Decimal
    islr: Decimal
    otras_deducciones: Decimal
    total_deducciones: Decimal
    # Neto a pagar (devengado salarial + cestaticket − deducciones)
    total_asignaciones: Decimal
    neto_pagar: Decimal
    # Provisiones / pasivos laborales (no afectan el neto del período)
    provision_utilidades: Decimal
    provision_vacaciones: Decimal
    provision_bono_vacacional: Decimal
    provision_prestaciones: Decimal
    # Aportes patronales (costo empresa, informativo)
    aporte_patronal_sso: Decimal
    aporte_patronal_faov: Decimal
    aporte_patronal_inces: Decimal
    aporte_patronal_rpe: Decimal
    total_aportes_patronales: Decimal

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# ── Helpers de base ──────────────────────────────────────────────────────────


def salario_diario(salario_mensual, params: ParametrosLOTTT) -> Decimal:
    return _d(salario_mensual) / Decimal(params.dias_mes)


def valor_hora(salario_mensual, params: ParametrosLOTTT) -> Decimal:
    return _d(salario_mensual) / params.horas_jornada_mensual


def calcular_islr(base_mensual_gravable: Decimal, params: ParametrosLOTTT) -> Decimal:
    """ISLR mensual: anualiza la base, ubica el tramo en UT y prorratea a 1 mes.

    Simplificación documentada (ver encabezado del módulo). Si `aplica_islr` es
    False (trabajador bajo el umbral exento) devuelve 0.
    """
    if not params.aplica_islr or base_mensual_gravable <= 0:
        return Decimal("0")
    base_anual = _d(base_mensual_gravable) * Decimal("12")
    base_anual_ut = base_anual / params.valor_ut
    impuesto_anual_ut = Decimal("0")
    for tramo in params.tramos_islr:
        if base_anual_ut > tramo.desde_ut and (tramo.hasta_ut is None or base_anual_ut <= tramo.hasta_ut):
            impuesto_anual_ut = base_anual_ut * tramo.tasa - tramo.sustraendo_ut
            break
    if impuesto_anual_ut <= 0:
        return Decimal("0")
    impuesto_anual = impuesto_anual_ut * params.valor_ut
    return q(impuesto_anual / Decimal("12"))


# ── Cálculo principal ────────────────────────────────────────────────────────


def calcular_nomina(entrada: EntradaNomina, params: ParametrosLOTTT | None = None) -> ResultadoNomina:
    """Calcula la nómina de un trabajador para un período (todo en Decimal)."""
    p = params or ParametrosLOTTT()
    sal_mensual = _d(entrada.salario_mensual)
    sal_dia = salario_diario(sal_mensual, p)
    val_hora = valor_hora(sal_mensual, p)

    # ── Devengados salariales ──
    salario_periodo = q(sal_dia * Decimal(entrada.dias_trabajados))
    monto_he_diurna = q(_d(entrada.horas_extra_diurnas) * val_hora * (Decimal("1") + p.recargo_hora_extra_diurna))
    monto_he_nocturna = q(_d(entrada.horas_extra_nocturnas) * val_hora * (Decimal("1") + p.recargo_hora_extra_nocturna))
    monto_bono_nocturno = q(_d(entrada.horas_nocturnas) * val_hora * p.recargo_bono_nocturno)
    otras_asig = q(entrada.otras_asignaciones)

    total_dev_salarial = q(
        salario_periodo + monto_he_diurna + monto_he_nocturna + monto_bono_nocturno + otras_asig
    )

    # ── Deducciones (sobre el devengado salarial) ──
    sso = q(total_dev_salarial * p.sso_empleado)
    faov = q(total_dev_salarial * p.faov_empleado)
    rpe = q(total_dev_salarial * p.rpe_empleado)
    islr = calcular_islr(total_dev_salarial, p)
    otras_ded = q(entrada.otras_deducciones)
    total_ded = q(sso + faov + rpe + islr + otras_ded)

    # ── Asignaciones no salariales ──
    cestaticket = q(entrada.cestaticket_mensual)

    total_asignaciones = q(total_dev_salarial + cestaticket)
    neto = q(total_asignaciones - total_ded)

    # ── Provisiones (mensualizadas) ──
    prov_utilidades = q(sal_dia * Decimal(p.dias_utilidades_anuales) / Decimal("12"))
    dias_vac = Decimal(p.dias_vacaciones_anuales) + min(
        Decimal(entrada.antiguedad_anios) * Decimal(p.dias_adicionales_vacaciones_por_anio),
        Decimal(p.tope_dias_adicionales_vacaciones),
    )
    prov_vacaciones = q(sal_dia * dias_vac / Decimal("12"))
    prov_bono_vac = q(sal_dia * Decimal(p.dias_bono_vacacional_anuales) / Decimal("12"))
    # Prestaciones (garantía): 15 días/trimestre = 5 días/mes + adicionales/año
    dias_prest_mes = Decimal(p.dias_prestaciones_trimestre) / Decimal("3")
    dias_adic_mes = (
        Decimal(max(entrada.antiguedad_anios - 1, 0)) * Decimal(p.dias_prestaciones_adicionales_anuales)
    ) / Decimal("12")
    prov_prestaciones = q(sal_dia * (dias_prest_mes + dias_adic_mes))

    # ── Aportes patronales (informativos) ──
    ap_sso = q(total_dev_salarial * p.sso_patronal)
    ap_faov = q(total_dev_salarial * p.faov_patronal)
    ap_inces = q(total_dev_salarial * p.inces_patronal)
    ap_rpe = q(total_dev_salarial * p.rpe_patronal)
    total_aportes = q(ap_sso + ap_faov + ap_inces + ap_rpe)

    return ResultadoNomina(
        salario_periodo=salario_periodo,
        monto_horas_extra_diurnas=monto_he_diurna,
        monto_horas_extra_nocturnas=monto_he_nocturna,
        monto_bono_nocturno=monto_bono_nocturno,
        otras_asignaciones=otras_asig,
        total_devengado_salarial=total_dev_salarial,
        cestaticket=cestaticket,
        sso=sso,
        faov=faov,
        rpe=rpe,
        islr=islr,
        otras_deducciones=otras_ded,
        total_deducciones=total_ded,
        total_asignaciones=total_asignaciones,
        neto_pagar=neto,
        provision_utilidades=prov_utilidades,
        provision_vacaciones=prov_vacaciones,
        provision_bono_vacacional=prov_bono_vac,
        provision_prestaciones=prov_prestaciones,
        aporte_patronal_sso=ap_sso,
        aporte_patronal_faov=ap_faov,
        aporte_patronal_inces=ap_inces,
        aporte_patronal_rpe=ap_rpe,
        total_aportes_patronales=total_aportes,
    )
