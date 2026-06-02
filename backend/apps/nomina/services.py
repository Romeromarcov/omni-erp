"""Orquestación de nómina (Ola 5.2).

Mapea entidades del ORM (Empleado, PeriodoNomina) a la entrada del motor de
cálculo PURO `calculo_lottt` y devuelve el resultado. La lógica monetaria vive
en `calculo_lottt` (sin I/O, testeable); aquí solo se extraen datos.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from .calculo_lottt import EntradaNomina, ParametrosLOTTT, ResultadoNomina, calcular_nomina

logger = logging.getLogger(__name__)


def _salario_mensual(empleado) -> Decimal:
    """Lee el salario mensual del empleado de forma defensiva (varios nombres
    posibles según evolucione el modelo de rrhh)."""
    for attr in ("salario_mensual", "sueldo_base", "salario_base", "salario"):
        val = getattr(empleado, attr, None)
        if val is not None:
            return Decimal(str(val))
    return Decimal("0")


def _antiguedad_anios(empleado, periodo) -> int:
    fecha_ingreso = getattr(empleado, "fecha_ingreso", None)
    fecha_corte = getattr(periodo, "fecha_fin", None) or getattr(periodo, "fecha_pago", None)
    if not fecha_ingreso or not fecha_corte:
        return 0
    return max((fecha_corte - fecha_ingreso).days // 365, 0)


def entrada_desde_empleado(
    empleado,
    periodo,
    *,
    dias_trabajados: int = 30,
    horas_extra_diurnas: Decimal = Decimal("0"),
    horas_extra_nocturnas: Decimal = Decimal("0"),
    horas_nocturnas: Decimal = Decimal("0"),
    cestaticket_mensual: Decimal = Decimal("0"),
    otras_asignaciones: Decimal = Decimal("0"),
    otras_deducciones: Decimal = Decimal("0"),
) -> EntradaNomina:
    return EntradaNomina(
        salario_mensual=_salario_mensual(empleado),
        dias_trabajados=dias_trabajados,
        horas_extra_diurnas=horas_extra_diurnas,
        horas_extra_nocturnas=horas_extra_nocturnas,
        horas_nocturnas=horas_nocturnas,
        antiguedad_anios=_antiguedad_anios(empleado, periodo),
        cestaticket_mensual=cestaticket_mensual,
        otras_asignaciones=otras_asignaciones,
        otras_deducciones=otras_deducciones,
    )


def calcular_nomina_empleado(
    empleado,
    periodo,
    *,
    parametros: ParametrosLOTTT | None = None,
    **kwargs,
) -> ResultadoNomina:
    """Calcula la nómina LOTTT de un empleado para un período (Decimal end-to-end)."""
    entrada = entrada_desde_empleado(empleado, periodo, **kwargs)
    return calcular_nomina(entrada, parametros)
