# apps/core/apps.py

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self):
        # Registra el signal connection_created que fija el contexto RLS por
        # defecto en cada conexión nueva (ver apps/core/signals.py).
        from . import signals  # noqa: F401
