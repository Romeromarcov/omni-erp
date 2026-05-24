"""
Management command para consumir eventos desde Redpanda/Kafka.

Uso:
    python manage.py consumir_eventos
    python manage.py consumir_eventos --topics omni.ventas omni.inventario
    python manage.py consumir_eventos --topics omni.ventas --group mi-grupo
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Consume eventos desde Redpanda/Kafka (Redpanda-compatible)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--topics",
            nargs="+",
            default=["omni.ventas", "omni.inventario", "omni.finanzas"],
            help="Lista de topics a suscribir (default: omni.ventas omni.inventario omni.finanzas)",
        )
        parser.add_argument(
            "--group",
            default="omni-erp-consumer",
            help="Consumer group ID (default: omni-erp-consumer)",
        )
        parser.add_argument(
            "--poll-timeout",
            type=float,
            default=1.0,
            dest="poll_timeout",
            help="Timeout en segundos por ciclo de poll (default: 1.0)",
        )

    def handle(self, *args, **options):
        topics = options["topics"]
        group = options["group"]
        poll_timeout = options["poll_timeout"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Iniciando OmniEventConsumer — topics={topics} group={group}"
            )
        )

        from apps.eventos.consumers import run_consumer

        try:
            run_consumer(
                topics=topics,
                group_id=group,
                poll_timeout=poll_timeout,
            )
        except KeyboardInterrupt:
            pass

        self.stdout.write(self.style.WARNING("OmniEventConsumer finalizado."))
