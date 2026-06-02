from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auditoria"

    def ready(self):
        # NEW-DOC-2: las señales de auditoría viven en apps/auditoria/signals.py.
        from . import signals

        signals.connect_signals()
