"""Tareas Celery multi-tenant de escalación por SLA de aprobaciones."""

from __future__ import annotations

from typing import Any

from celery import shared_task

from apps.core import rls  # noqa: F401 — el contexto RLS por empresa se aplica en el servicio

from .services import escalar_solicitudes_vencidas as _escalar_solicitudes_vencidas


@shared_task(name="gestion_aprobaciones.escalar_solicitudes_vencidas")
def escalar_solicitudes_vencidas() -> dict[str, Any]:
    """Escala solicitudes pendientes cuyo SLA en horas haya expirado (rls_bypass + rls_tenant_context)."""
    return _escalar_solicitudes_vencidas()
