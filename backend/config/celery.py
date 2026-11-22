"""
Celery application instance para Omni ERP.

Se carga automáticamente al arrancar Django gracias a la importación
en config/__init__.py. Todos los módulos apps.*  pueden definir un
archivo tasks.py y sus tareas se registran automáticamente.
"""

import logging
import os

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

logger = logging.getLogger(__name__)

# Asegurar que Django sepa qué settings usar antes de cargar Celery.
# DEBE ser el dispatcher "config.settings" (no settings_dev): config/__init__.py
# importa este módulo al cargar el paquete `config`, así que cuando uvicorn/gunicorn
# importan `config.asgi`/`config.wsgi`, este setdefault corre PRIMERO. Si apuntara a
# settings_dev, ganaría sobre el setdefault("config.settings") de asgi/wsgi y el
# servidor arrancaría en modo dev (DEBUG=True, ALLOWED_HOSTS de dev) en producción.
# Con el dispatcher, DJANGO_ENV decide dev/prod de forma coherente en todos los procesos.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("omni_erp")

# Leer configuración desde settings de Django, prefijo CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-descubrir tareas en todos los módulos instalados
app.autodiscover_tasks()


@worker_process_init.connect(weak=False)
def _init_celery_telemetry(**_kwargs):
    """
    Inicializa OpenTelemetry en cada worker tras fork() cuando OTEL_ENABLED=true.

    Se conecta a ``worker_process_init`` (y no a nivel de módulo) para evitar
    compartir hilos del ``BatchSpanProcessor`` entre el proceso padre y los hijos.
    """
    try:
        from apps.core.telemetry import init_telemetry, is_telemetry_enabled

        if is_telemetry_enabled():
            init_telemetry(service_name=os.environ.get("OTEL_SERVICE_NAME") or "omni-erp-worker")
    except Exception as exc:  # noqa: BLE001 - nunca bloquear arranque del worker
        logger.warning("OTel Celery worker init omitido (%s).", type(exc).__name__)


@worker_process_shutdown.connect(weak=False)
def _shutdown_celery_telemetry(**_kwargs):
    """Hace flush limpio de spans al apagar el proceso worker de Celery."""
    try:
        from apps.core.telemetry import is_telemetry_enabled, shutdown_telemetry

        if is_telemetry_enabled():
            shutdown_telemetry()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OTel Celery worker shutdown omitido (%s).", type(exc).__name__)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Tarea de diagnóstico — registra la request de Celery."""
    logger.info("Request: %r", self.request)
