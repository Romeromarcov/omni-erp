from django.apps import AppConfig


class ConfiguracionMotorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.configuracion_motor"

    def ready(self) -> None:
        from . import signals  # noqa: F401  # side-effect: registra signals de invalidación de caché
