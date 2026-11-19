"""Tareas Celery de activaciones: la sync con Google Calendar no debe bloquear la petición HTTP."""

from __future__ import annotations

import logging
import uuid

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="activaciones.sincronizar_google")
def sincronizar_google_task(evento_id: str) -> None:
    from apps.core import rls

    from .models import EventoActivacion
    from .services import sincronizar_google

    empresa_id = None
    try:
        uuid.UUID(str(evento_id))
    except (ValueError, TypeError, AttributeError):
        empresa_id = None
    else:
        with rls.rls_bypass():
            empresa_id = EventoActivacion.objects.filter(pk=evento_id).values_list("id_empresa_id", flat=True).first()

    if empresa_id is not None:
        with rls.rls_tenant_context([empresa_id]):
            sincronizar_google(evento_id)
    else:
        sincronizar_google(evento_id)


def encolar_sync(evento_id) -> None:
    """Encola la sync; si el broker no responde, el evento ya está guardado (se reintenta al editarlo)."""
    try:
        # retry=False: con el broker caído falla al instante (el evento ya está guardado) en vez de bloquear
        # la petición varios segundos con los reintentos de publicación.
        sincronizar_google_task.apply_async(args=[str(evento_id)], retry=False)
    except Exception:  # un broker caído no debe romper el alta del evento
        logger.exception("No se pudo encolar la sync de Google Calendar (evento %s)", evento_id)
