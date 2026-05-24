"""
Tareas Celery del módulo de Agentes IA.

generar_sugerencias_diarias():
  Ejecuta CobranzaEstrategaAgent y ReordenSugeridorAgent para todas las empresas
  activas, persistiendo PrediccionAgente con resultado_humano="pendiente".
  Programada para correr a las 06:00 AM cada día (configurada en Celery Beat).
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("agentes")


@shared_task(
    name="agentes.generar_sugerencias_diarias",
    bind=True,
    max_retries=2,
    default_retry_delay=300,  # 5 min retry
)
def generar_sugerencias_diarias(self):
    """
    Genera sugerencias diarias de cobranza y reorden para todas las empresas activas.

    Para cada empresa:
    - CobranzaEstrategaAgent: crea predicciones para CxC vencidas con prioridad ALTA.
    - ReordenSugeridorAgent: crea predicciones para productos en umbral de reorden.

    Solo persiste predicciones nuevas; no duplica las del mismo día.
    """
    from apps.core.models import Empresa

    empresas = Empresa.objects.filter(activo=True) if hasattr(Empresa, "activo") else Empresa.objects.all()
    total_sugerencias = 0

    for empresa in empresas:
        total_sugerencias += _generar_cobranza(empresa)
        total_sugerencias += _generar_reorden(empresa)

    logger.info("generar_sugerencias_diarias: %d sugerencias creadas para %d empresas.", total_sugerencias, empresas.count())
    return {"total_sugerencias": total_sugerencias, "empresas": empresas.count()}


def _generar_cobranza(empresa) -> int:
    """Genera sugerencias de cobranza para una empresa. Retorna cantidad creada."""
    try:
        from .cobranza import CobranzaEstrategaAgent

        agente = CobranzaEstrategaAgent(empresa=empresa)
        sugerencias = agente.analizar(persistir=True)
        # Solo contar las de prioridad ALTA para el reporte
        count = sum(1 for s in sugerencias if getattr(s, "prioridad", "") == "ALTA")
        return count
    except Exception as exc:
        logger.warning("Cobranza para empresa %s: %s", empresa.pk, exc)
        return 0


def _generar_reorden(empresa) -> int:
    """Genera sugerencias de reorden para una empresa. Retorna cantidad creada."""
    try:
        from .reorden import ReordenSugeridorAgent

        agente = ReordenSugeridorAgent(empresa=empresa)
        sugerencias = agente.analizar(solo_alertas=True, persistir=True)
        return len(sugerencias)
    except Exception as exc:
        logger.warning("Reorden para empresa %s: %s", empresa.pk, exc)
        return 0
