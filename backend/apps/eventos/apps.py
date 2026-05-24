from django.apps import AppConfig


class EventosConfig(AppConfig):
    name = "apps.eventos"
    verbose_name = "Eventos (Event Store)"

    def ready(self):
        import apps.eventos.signals  # noqa: F401
