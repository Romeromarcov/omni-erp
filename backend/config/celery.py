"""
Celery application instance para Omni ERP.

Se carga automáticamente al arrancar Django gracias a la importación
en config/__init__.py. Todos los módulos apps.*  pueden definir un
archivo tasks.py y sus tareas se registran automáticamente.
"""

import os

from celery import Celery

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


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Tarea de diagnóstico — imprime la request de Celery."""
    print(f"Request: {self.request!r}")
