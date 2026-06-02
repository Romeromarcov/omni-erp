from django.apps import AppConfig


class LocalizacionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.localizacion"
    verbose_name = "Localización (framework de puertos)"

    def ready(self):
        # Registrar las localizaciones disponibles al arrancar.
        from . import registry  # noqa: F401
