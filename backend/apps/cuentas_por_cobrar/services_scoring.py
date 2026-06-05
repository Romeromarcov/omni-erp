"""
Scoring de cobrabilidad.

Fórmula portada de GestionCxC:
score = (dias_vencida × 3) + (monto_pendiente / 100) + (intentos_sin_respuesta × 5)

Mayor score = cliente más urgente de cobrar.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from apps.cuentas_por_cobrar.services_aging import PartidaCartera

logger = logging.getLogger(__name__)


@dataclass
class ScoreInput:
    dias_vencida: int
    monto_pendiente: Decimal
    intentos_sin_respuesta: int = 0


def calcular_score(inp: ScoreInput) -> Decimal:
    """
    score = (dias_vencida × 3) + (monto_pendiente / 100) + (intentos_sin_respuesta × 5)
    """
    return (
        Decimal(inp.dias_vencida) * Decimal("3")
        + inp.monto_pendiente / Decimal("100")
        + Decimal(inp.intentos_sin_respuesta) * Decimal("5")
    )


def priorizar(
    partidas: list[PartidaCartera],
    intentos_map: dict | None = None,
) -> list[dict]:
    """
    Filtra solo partidas vencidas, calcula score para cada una,
    devuelve lista de dicts ordenados por score DESC.

    Args:
        partidas:     Lista de PartidaCartera.
        intentos_map: {cliente_id: n_intentos_sin_respuesta} — opcional.

    Returns:
        Lista de dicts con: cliente_id, cliente_nombre, orden_ref,
        monto_pendiente, dias_vencida, bucket, score (ordenado DESC).
    """
    if intentos_map is None:
        intentos_map = {}

    scored = []
    for p in partidas:
        if not p.vencida:
            continue
        inp = ScoreInput(
            dias_vencida=p.dias_vencida,
            monto_pendiente=p.monto_pendiente,
            intentos_sin_respuesta=intentos_map.get(p.cliente_id, 0),
        )
        score = calcular_score(inp)
        scored.append({
            "cliente_id": p.cliente_id,
            "cliente_nombre": p.cliente_nombre,
            "orden_ref": p.orden_ref,
            "monto_pendiente": str(p.monto_pendiente),
            "dias_vencida": p.dias_vencida,
            "bucket": p.bucket,
            "score": str(score),
        })

    scored.sort(key=lambda x: Decimal(str(x["score"])), reverse=True)
    return scored
