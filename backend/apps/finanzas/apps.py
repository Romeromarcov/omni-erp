from django.apps import AppConfig


class FinanzasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.finanzas"
    verbose_name = "Finanzas"

    def ready(self) -> None:
        from . import signals  # noqa: F401  # side-effect: registra signals de invalidación de caché
