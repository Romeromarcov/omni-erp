# apps/core/apps.py

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self):
        # Registra los signals de apps.core (connection_created, pre/post_migrate
        # e invalidación de cache de visibilidad; ver apps/core/signals.py).
        from . import signals  # noqa: F401  # side-effect: registra signals
