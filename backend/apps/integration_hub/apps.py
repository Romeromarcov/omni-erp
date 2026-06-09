from django.apps import AppConfig


class IntegrationHubConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integration_hub"
    verbose_name = "Integration Hub"

    def ready(self):
        # Registrar conectores al iniciar la app
        from apps.integration_hub.connectors.registry import registry
        from apps.integration_hub.connectors.odoo.connector import OdooConnector
        from apps.integration_hub.connectors.google_sheets.connector import (
            GoogleSheetsConnector,
        )
        registry.register(OdooConnector)
        registry.register(GoogleSheetsConnector)
