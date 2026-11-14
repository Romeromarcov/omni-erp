from django.apps import AppConfig


class BotsIngestConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bots_ingest"
    verbose_name = "Ingesta desde bots (Telegram)"
