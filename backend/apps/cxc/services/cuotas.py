"""
Algoritmo de generación de cuotas para AcuerdoPago.

Portado de GestionCxC/backend/routers/acuerdos_pago.py → _generar_cuotas().
Sin efectos secundarios — el caller hace bulk_create en @transaction.atomic.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

logger = logging.getLogger(__name__)


def _proxima_fecha(fecha_base: date, periodicidad: str, n: int) -> date:
    """Calcula la fecha de la n-ésima cuota (base 1) dado periodicidad."""
    if periodicidad == "semanal":
        return fecha_base + timedelta(weeks=n)
    if periodicidad == "quincenal":
        return fecha_base + timedelta(days=15 * n)
    if periodicidad == "mensual":
        # Sumar n meses — manejo de fin de mes
        mes = fecha_base.month + n
        anio = fecha_base.year + (mes - 1) // 12
        mes = ((mes - 1) % 12) + 1
        import calendar
        ultimo_dia = calendar.monthrange(anio, mes)[1]
        dia = min(fecha_base.day, ultimo_dia)
        return date(anio, mes, dia)
    # unico
    return fecha_base


def generar_cuotas(
    acuerdo,
    fecha_inicio: date,
    plazo_total_dias: int,
    periodicidad: str,
    monto_total: Decimal,
    monto_cuota: Optional[Decimal] = None,
    porcentaje_abono: Optional[Decimal] = None,
) -> list[dict]:
    """
    Genera lista de dicts para CuotaAcuerdo.objects.bulk_create().

    Reglas:
    - Si periodicidad='unico': 1 cuota con monto_total completo.
    - Si monto_cuota: monto fijo, ajuste de redondeo en última cuota.
    - Si porcentaje_abono: monto = total × (pct/100), ajuste en última.
    - Si ninguno: divide total / num_cuotas, ajuste en última.

    Args:
        acuerdo:          Instancia AcuerdoPago (necesaria para FK).
        fecha_inicio:     Fecha de la primera cuota.
        plazo_total_dias: Plazo total del acuerdo en días.
        periodicidad:     'unico' | 'semanal' | 'quincenal' | 'mensual'
        monto_total:      Monto total del acuerdo.
        monto_cuota:      Monto fijo por cuota (opcional).
        porcentaje_abono: Porcentaje del total por cuota (0-100, opcional).

    Returns:
        Lista de dicts con keys: acuerdo, numero_cuota, fecha_vencimiento, monto, estado
    """
    CENTAVOS = Decimal("0.01")

    # BUG-M3: defensa en el service además del serializer.
    if monto_total <= 0:
        raise ValueError("monto_total debe ser mayor que cero.")

    if periodicidad == "unico":
        return [{
            "acuerdo": acuerdo,
            "numero_cuota": 1,
            "fecha_vencimiento": fecha_inicio,
            "monto": monto_total.quantize(CENTAVOS, rounding=ROUND_HALF_UP),
            "estado": "pendiente",
        }]

    # Calcular número de cuotas
    if periodicidad == "semanal":
        dias_por_cuota = 7
    elif periodicidad == "quincenal":
        dias_por_cuota = 15
    else:  # mensual
        dias_por_cuota = 30

    num_cuotas = max(1, plazo_total_dias // dias_por_cuota)

    # Calcular monto por cuota
    if monto_cuota:
        monto_unit = monto_cuota.quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    elif porcentaje_abono:
        monto_unit = (monto_total * porcentaje_abono / Decimal("100")).quantize(
            CENTAVOS, rounding=ROUND_HALF_UP
        )
    else:
        monto_unit = (monto_total / Decimal(num_cuotas)).quantize(
            CENTAVOS, rounding=ROUND_HALF_UP
        )

    cuotas = []
    acumulado = Decimal("0")

    for i in range(1, num_cuotas + 1):
        fecha_vcto = _proxima_fecha(fecha_inicio, periodicidad, i - 1)

        # BUG-M3: nunca emitir cuotas por más del total del acuerdo.
        restante = monto_total - acumulado
        if restante <= 0:
            break

        if i == num_cuotas:
            # Última cuota: ajustar diferencia de redondeo
            monto_esta = restante.quantize(CENTAVOS, rounding=ROUND_HALF_UP)
        else:
            # Capear cada cuota intermedia al restante (monto_cuota fijo puede
            # exceder el total: 100 total / cuotas de 80 → 80 + 20, no 80 + 80).
            monto_esta = min(monto_unit, restante.quantize(CENTAVOS, rounding=ROUND_HALF_UP))

        if monto_esta <= 0:
            continue

        cuotas.append({
            "acuerdo": acuerdo,
            "numero_cuota": i,
            "fecha_vencimiento": fecha_vcto,
            "monto": monto_esta,
            "estado": "pendiente",
        })
        acumulado += monto_esta

    return cuotas
