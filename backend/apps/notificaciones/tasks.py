"""Tareas Celery del módulo notificaciones."""

import logging

from celery import shared_task
from django.core.mail import send_mail
from django.template import Context, Template

logger = logging.getLogger("apps.notificaciones")


@shared_task(
    name="notificaciones.enviar_notificacion_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def enviar_notificacion_email(self, id_plantilla: str, destinatario: str, contexto: dict, id_log: str | None = None):
    """
    Envía un email usando la plantilla especificada.

    Reintentos automáticos con backoff en caso de fallo (máx. 3 intentos).
    """
    from apps.notificaciones.models import LogNotificacion, PlantillaNotificacion

    log = None
    if id_log:
        try:
            log = LogNotificacion.objects.get(id_log=id_log)
            log.intentos += 1
            log.save(update_fields=["intentos"])
        except LogNotificacion.DoesNotExist:
            pass

    try:
        plantilla = PlantillaNotificacion.objects.get(id_plantilla=id_plantilla)

        asunto = Template(plantilla.asunto).render(Context(contexto))
        cuerpo_html = Template(plantilla.cuerpo_html).render(Context(contexto))

        send_mail(
            subject=asunto,
            message="",  # plain text vacío; se usa html_message
            from_email=None,  # usa DEFAULT_FROM_EMAIL de settings
            recipient_list=[destinatario],
            html_message=cuerpo_html,
            fail_silently=False,
        )

        if log:
            log.estado = "ENVIADO"
            log.error = ""
            log.save(update_fields=["estado", "error"])

        logger.info("Email enviado: %s → %s", plantilla.codigo_plantilla, destinatario)

    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        logger.error("Error enviando email a %s: %s", destinatario, error_msg)

        if log:
            log.estado = "FALLIDO"
            log.error = error_msg
            log.save(update_fields=["estado", "error"])

        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Máximo de reintentos alcanzado para email a %s", destinatario)
