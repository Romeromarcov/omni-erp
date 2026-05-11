"""
Tareas Celery del módulo core.

Estas tareas sirven como smoke-test del bus de mensajes y como
utilidades transversales reutilizables por otros módulos.
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(name='core.ping', bind=True, max_retries=0)
def ping(self) -> dict:
    """
    Tarea de health-check del worker.

    Retorna un diccionario con el id de la tarea y el mensaje 'pong'.
    Útil para verificar que el worker está activo y respondiendo.

    Returns:
        dict: {'task_id': str, 'status': 'pong'}
    """
    logger.info('core.ping ejecutado — task_id=%s', self.request.id)
    return {'task_id': self.request.id, 'status': 'pong'}


@shared_task(name='core.log_evento', bind=True, max_retries=3, default_retry_delay=5)
def log_evento(self, nivel: str, mensaje: str, modulo: str = 'core') -> dict:
    """
    Registra un evento de aplicación de forma asíncrona.

    Parámetros:
        nivel   — 'info' | 'warning' | 'error'
        mensaje — Texto libre del evento
        modulo  — Módulo Django que originó el evento (default 'core')

    Retorna el mismo dict de entrada enriquecido con el task_id.
    """
    log_fn = {
        'info': logger.info,
        'warning': logger.warning,
        'error': logger.error,
    }.get(nivel.lower(), logger.info)

    log_fn('[%s] %s — task_id=%s', modulo, mensaje, self.request.id)

    return {
        'task_id': self.request.id,
        'nivel': nivel,
        'modulo': modulo,
        'mensaje': mensaje,
    }
