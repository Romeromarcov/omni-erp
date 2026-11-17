"""Tareas Celery multi-tenant de recurrencia, recordatorios y escalación (ADR-015)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from apps.core.models import Empresa

from .services import ejecutar_seguimiento_empresa, generar_tareas_recurrentes_pendientes

logger = logging.getLogger(__name__)


@shared_task(name="tareas.ejecutar_ciclo_empresa")
def ejecutar_ciclo_empresa(empresa_id: str, momento: str = "AUTO") -> dict[str, Any]:
    """Genera tareas recurrentes vencidas y evalúa recordatorios/escalación para ``empresa_id``."""
    empresa = Empresa.objects.filter(id_empresa=empresa_id, activo=True).first()
    if empresa is None:
        logger.warning("tareas.ejecutar_ciclo_empresa: empresa %s inactiva o inexistente", empresa_id)
        return {"empresa_id": str(empresa_id), "omitida": True}

    rec = generar_tareas_recurrentes_pendientes(empresa)
    seg = ejecutar_seguimiento_empresa(empresa, momento=momento)
    return {
        "empresa_id": str(empresa.id_empresa),
        "recurrentes_creadas": rec["tareas_creadas"],
        "alertas_emitidas": seg["alertas_emitidas"],
        "tareas_bloqueadas": seg["tareas_bloqueadas"],
    }


@shared_task(name="tareas.ejecutar_ciclo_todos")
def ejecutar_ciclo_todos(momento: str = "AUTO") -> dict[str, Any]:
    """Itera de forma aislada sobre todas las empresas activas para disparar su ciclo operativo."""
    ids = list(
        Empresa.objects.filter(activo=True).values_list("id_empresa", flat=True)
    )
    procesadas = 0
    errores = 0
    for emp_id in ids:
        try:
            ejecutar_ciclo_empresa(str(emp_id), momento=momento)
            procesadas += 1
        except Exception:  # noqa: BLE001
            errores += 1
            logger.exception("Fallo en ciclo de tareas para empresa %s", emp_id)

    return {"empresas_procesadas": procesadas, "errores": errores}
