"""Conciliación de facturación (sección 7) — parte PURA del semáforo.

El motor dice lo que la factura DEBERÍA ser (``total_motor``); Odoo dice lo que
FUE (``monto_facturado`` − NCs). El sistema marca la brecha con un semáforo. No
escribe nada a Odoo (write-back purista).

Este módulo porta SOLO la pieza determinística ``clasificar_diferencia``. Los
lectores Odoo / repositorios (``OdooFacturasReader``, ``Reconciler``) son
infraestructura de Fase 4/5 y NO se portan aquí.

Bandas del semáforo (interpretación de las tres bandas de la sección 7):
    |dif| <= tolerancia_redondeo            -> VERDE   (cuadra)
    tolerancia_redondeo < |dif| <= roja     -> AMARILLO (revisar)
    |dif| > tolerancia_roja                 -> ROJO    (se facturó distinto)
"""

from __future__ import annotations

from decimal import Decimal

from .config import ReconciliationConfig
from .decimal_utils import q2
from .models import Conciliacion, ResultadoConciliacion


def clasificar_diferencia(
    total_motor: Decimal,
    monto_odoo: Decimal,
    ncs_odoo: Decimal,
    config: ReconciliationConfig,
) -> Conciliacion:
    """Compara el neto del motor contra el neto real de Odoo y aplica el semáforo."""
    neto_odoo = monto_odoo - ncs_odoo
    diferencia = q2(total_motor - neto_odoo)
    magnitud = abs(diferencia)
    if magnitud <= config.tolerance_rounding:
        resultado = ResultadoConciliacion.VERDE
    elif magnitud <= config.tolerance_red:
        resultado = ResultadoConciliacion.AMARILLO
    else:
        resultado = ResultadoConciliacion.ROJO
    return Conciliacion(
        so_id="",  # lo fija el runner
        total_motor=q2(total_motor),
        monto_odoo=q2(monto_odoo),
        ncs_odoo=q2(ncs_odoo),
        diferencia=diferencia,
        resultado=resultado,
    )
