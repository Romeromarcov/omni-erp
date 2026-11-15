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
        # retry=False: con el broker caído falla al instante (el evento ya está guardado) en vez de bloquear
        # la petición varios segundos con los reintentos de publicación.
        sincronizar_google_task.apply_async(args=[str(evento_id)], retry=False)
    except Exception:  # noqa: BLE001 - un broker caído no debe romper el alta del evento
        logger.exception(
            "No se pudo encolar la sync de Google Calendar (evento %s)", evento_id
        )
