from django.apps import AppConfig


class AgentesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agentes"
    verbose_name = "Agentes IA"

    def ready(self) -> None:
        from .services import registrar_hook_consumo_llm  # noqa: PLC0415

        registrar_hook_consumo_llm(force=False)
