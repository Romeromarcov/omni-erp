"""
Celery application instance para Omni ERP.

Se carga automáticamente al arrancar Django gracias a la importación
en config/__init__.py. Todos los módulos apps.*  pueden definir un
archivo tasks.py y sus tareas se registran automáticamente.
"""

import os

from celery import Celery

# Asegurar que Django sepa qué settings usar antes de cargar Celery
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_dev")

app = Celery("omni_erp")

# Leer configuración desde settings de Django, prefijo CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-descubrir tareas en todos los módulos instalados
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Tarea de diagnóstico — imprime la request de Celery."""
    print(f"Request: {self.request!r}")
