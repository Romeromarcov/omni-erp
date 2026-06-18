"""Persistencia del costeo real de una orden de fabricación (Sub-fase 1.I).

`manufactura.services.costeo_real_orden` calcula el costo real de una OF pero no
lo guarda; la app `costos` quedaba sin datos. Este módulo materializa ese cálculo
como registros `CostoProduccion` (uno por tipo de costo) cuando la OF se cierra,
habilitando el reporte de costos y el análisis de variación.

Reglas: Decimal en todo (R-CODE-4), atómico (R-CODE-11), aislado por empresa
(R-CODE-1) e idempotente (no duplica si la OF ya fue costeada).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

# Mapa tipo de CostoProduccion → clave del dict de costeo_real_orden.
_TIPOS = (
    ("MATERIAL_DIRECTO", "costo_materiales"),
    ("MANO_OBRA_DIRECTA", "mano_obra"),
    ("COSTOS_INDIRECTOS", "costos_indirectos"),
)

_CUATRO = Decimal("0.0001")


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


@transaction.atomic
def persistir_costos_orden(orden, *, fecha_hora=None, forzar=False):
    """Crea los `CostoProduccion` de la OF a partir de su costeo real.

    - Idempotente: si la OF ya tiene costos activos no crea duplicados (salvo
      `forzar=True`, que desactiva los previos y recostea).
    - La cantidad base es lo realmente producido (suma de `ProduccionTerminada`),
      con fallback a la cantidad planificada de la OF.
    - Moneda: la moneda base de la empresa (`id_moneda_base`).

    Devuelve la lista de `CostoProduccion` creados (vacía si ya existían).
    """
    from apps.manufactura.models import ProduccionTerminada
    from apps.manufactura.services import ManufacturaError, costeo_real_orden

    from .models import CostoProduccion

    existentes = CostoProduccion.objects.filter(id_orden_produccion=orden, activo=True)
    if existentes.exists():
        if not forzar:
            return []
        existentes.update(activo=False)

    moneda = orden.empresa.id_moneda_base
    if moneda is None:
        raise ManufacturaError(
            "La empresa no tiene moneda base configurada; no se puede costear la orden."
        )

    producido = sum(
        (_d(p.cantidad) for p in ProduccionTerminada.objects.filter(orden_produccion=orden)),
        Decimal("0"),
    )
    if producido <= 0:
        producido = _d(orden.cantidad)

    costo = costeo_real_orden(orden, cantidad_producida=producido)
    fecha = fecha_hora or timezone.now()

    creados = []
    for tipo, clave in _TIPOS:
        total = _d(costo[clave])
        unitario = (total / producido).quantize(_CUATRO)
        creados.append(
            CostoProduccion.objects.create(
                id_empresa=orden.empresa,
                id_orden_produccion=orden,
                tipo_costo=tipo,
                costo_unitario=unitario,
                cantidad=producido,
                costo_total=total,
                id_moneda=moneda,
                fecha_calculo=fecha,
            )
        )
    return creados
