"""Tareas Celery de activaciones: la sync con Google Calendar no debe bloquear la petición HTTP."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="activaciones.sincronizar_google")
def sincronizar_google_task(evento_id: str) -> None:
    from .services import sincronizar_google

    sincronizar_google(evento_id)


def encolar_sync(evento_id) -> None:
    """Encola la sync; si el broker no responde, el evento ya está guardado (se reintenta al editarlo)."""
    try:
        sincronizar_google_task.delay(str(evento_id))
    except Exception:  # noqa: BLE001 - un broker caído no debe romper el alta del evento
        logger.exception(
            "No se pudo encolar la sync de Google Calendar (evento %s)", evento_id
        )
