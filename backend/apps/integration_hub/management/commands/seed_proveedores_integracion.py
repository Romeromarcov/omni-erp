"""Siembra/actualiza el catálogo base de proveedores de integración.

Idempotente (``update_or_create`` por ``codigo``). Lo corre el ``entrypoint.sh``
en cada deploy para garantizar que los proveedores base existan siempre, sin
depender de la migración de datos de una sola vez (que puede no reflejarse si la
BD del entorno se reprovisiona).

No desactiva ni borra proveedores que el administrador haya creado/editado desde
el Panel SaaS: solo hace upsert de los `PROVEEDORES_BASE`. Por defecto NO pisa el
campo ``estado``/``activo`` si la fila ya existe (para respetar cambios del admin);
con ``--forzar`` reescribe todos los campos al valor base.
"""

from django.core.management.base import BaseCommand

from apps.integration_hub.models import ConectorProveedor
from apps.integration_hub.seed_data import PROVEEDORES_BASE


class Command(BaseCommand):
    help = "Siembra/actualiza el catálogo base de proveedores de integración (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--forzar",
            action="store_true",
            help="Reescribe TODOS los campos base aunque la fila ya exista "
            "(incluye estado/activo). Sin esta bandera, una fila existente solo "
            "completa campos vacíos y respeta estado/activo editados por el admin.",
        )

    def handle(self, *args, **options):
        forzar = options["forzar"]
        creados = 0
        actualizados = 0

        for prov in PROVEEDORES_BASE:
            codigo = prov["codigo"]
            defaults = {k: v for k, v in prov.items() if k != "codigo"}
            existente = ConectorProveedor.objects.filter(codigo=codigo).first()

            if existente is None:
                ConectorProveedor.objects.create(codigo=codigo, **defaults)
                creados += 1
                continue

            if forzar:
                for campo, valor in defaults.items():
                    setattr(existente, campo, valor)
                existente.save(update_fields=list(defaults.keys()))
                actualizados += 1
            # Sin --forzar: la fila existe y se respeta tal cual (no pisar al admin).

        self.stdout.write(
            self.style.SUCCESS(
                f"Proveedores de integración: {creados} creados, "
                f"{actualizados} actualizados, "
                f"{ConectorProveedor.objects.count()} en catálogo."
            )
        )
