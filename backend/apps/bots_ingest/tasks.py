"""Tareas Celery de bots_ingest: el envío a Odoo no bloquea la petición del bot."""

from __future__ import annotations

import logging

from celery import shared_task

from .services.odoo_push import ErrorTransitorio

logger = logging.getLogger(__name__)


@shared_task(
    name="bots_ingest.sincronizar_odoo",
    autoretry_for=(ErrorTransitorio,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 4},
)
def sincronizar_odoo_task(ingesta_id: str) -> None:
    from .models import IngestaBot
    from .services import odoo_push

    ing = (
        IngestaBot.objects.select_related("bot_usuario__usuario", "id_empresa")
        .filter(pk=ingesta_id)
        .first()
    )
    if ing is not None:
        odoo_push.sincronizar(ing)


def encolar_sync(ingesta_id) -> None:
    """Encola el envío; con el broker caído la ingesta queda guardada y se puede reintentar a mano."""
    try:
        sincronizar_odoo_task.delay(str(ingesta_id))
    except Exception:  # noqa: BLE001 - un broker caído no debe romper la ingesta ya confirmada
        logger.exception("No se pudo encolar el envío a Odoo (ingesta %s)", ingesta_id)
