"""
Comando de gestión: migrar_contactos

Migra contactos entre empresas o fusiona duplicados.
Uso:
    python manage.py migrar_contactos --origen <empresa_id> --destino <empresa_id>
    python manage.py migrar_contactos --fusionar-duplicados --empresa <empresa_id>
    python manage.py migrar_contactos --dry-run
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import Empresa


class Command(BaseCommand):
    help = "Migra o fusiona contactos (clientes/proveedores) entre empresas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--origen",
            type=str,
            help="UUID de la empresa origen de los contactos a migrar.",
        )
        parser.add_argument(
            "--destino",
            type=str,
            help="UUID de la empresa destino donde se migrarán los contactos.",
        )
        parser.add_argument(
            "--empresa",
            type=str,
            help="UUID de la empresa para la operación de fusión de duplicados.",
        )
        parser.add_argument(
            "--fusionar-duplicados",
            action="store_true",
            default=False,
            help="Fusiona contactos duplicados (mismo RIF) dentro de una empresa.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Ejecuta sin modificar la base de datos (solo reporta qué haría).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY-RUN] Sin cambios en la base de datos."))

        if options["fusionar_duplicados"]:
            self._fusionar_duplicados(options["empresa"], dry_run)
        elif options["origen"] and options["destino"]:
            self._migrar_entre_empresas(options["origen"], options["destino"], dry_run)
        else:
            raise CommandError(
                "Debe especificar --fusionar-duplicados --empresa <id>  "
                "o  --origen <id> --destino <id>"
            )

    @transaction.atomic
    def _migrar_entre_empresas(self, origen_id, destino_id, dry_run):
        """Mueve contactos de la empresa origen a la empresa destino."""
        try:
            empresa_origen = Empresa.objects.get(pk=origen_id)
        except Empresa.DoesNotExist:
            raise CommandError(f"Empresa origen '{origen_id}' no encontrada.")

        try:
            empresa_destino = Empresa.objects.get(pk=destino_id)
        except Empresa.DoesNotExist:
            raise CommandError(f"Empresa destino '{destino_id}' no encontrada.")

        self.stdout.write(
            f"Migrando contactos de '{empresa_origen}' → '{empresa_destino}'"
        )

        # Importar dinámicamente para no crear dependencias circulares
        from apps.crm.models import Cliente
        from apps.proveedores.models import Proveedor

        clientes = Cliente.objects.filter(id_empresa=empresa_origen)
        proveedores = Proveedor.objects.filter(id_empresa=empresa_origen)

        self.stdout.write(f"  Clientes encontrados: {clientes.count()}")
        self.stdout.write(f"  Proveedores encontrados: {proveedores.count()}")

        if not dry_run:
            clientes_migrados = clientes.update(id_empresa=empresa_destino)
            proveedores_migrados = proveedores.update(id_empresa=empresa_destino)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Migrados: {clientes_migrados} clientes, {proveedores_migrados} proveedores."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY-RUN] Se migrarían {clientes.count()} clientes y "
                    f"{proveedores.count()} proveedores."
                )
            )

        if dry_run:
            transaction.set_rollback(True)

    @transaction.atomic
    def _fusionar_duplicados(self, empresa_id, dry_run):
        """Detecta y fusiona contactos con el mismo identificador fiscal dentro de una empresa."""
        if not empresa_id:
            raise CommandError("Debe especificar --empresa <id> junto con --fusionar-duplicados.")

        try:
            empresa = Empresa.objects.get(pk=empresa_id)
        except Empresa.DoesNotExist:
            raise CommandError(f"Empresa '{empresa_id}' no encontrada.")

        self.stdout.write(f"Buscando duplicados en '{empresa}'...")

        from django.db.models import Count

        from apps.crm.models import Cliente

        # Detectar RIFs duplicados
        duplicados = (
            Cliente.objects.filter(id_empresa=empresa)
            .values("identificador_fiscal")
            .annotate(total=Count("id_cliente"))
            .filter(total__gt=1)
        )

        total_grupos = duplicados.count()
        self.stdout.write(f"  Grupos de duplicados encontrados: {total_grupos}")

        if total_grupos == 0:
            self.stdout.write(self.style.SUCCESS("No hay duplicados. Base de datos limpia."))
            return

        fusionados = 0
        for grupo in duplicados:
            rif = grupo["identificador_fiscal"]
            clientes_dup = Cliente.objects.filter(
                id_empresa=empresa, identificador_fiscal=rif
            ).order_by("fecha_creacion")

            principal = clientes_dup.first()
            duplicados_a_eliminar = clientes_dup.exclude(pk=principal.pk)

            self.stdout.write(
                f"  RIF {rif}: conservando '{principal}', eliminando {duplicados_a_eliminar.count()} duplicado(s)."
            )

            if not dry_run:
                duplicados_a_eliminar.delete()
                fusionados += duplicados_a_eliminar.count()

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Fusionados: {fusionados} registros eliminados."))
        else:
            self.stdout.write(self.style.WARNING("[DRY-RUN] Sin cambios aplicados."))

        if dry_run:
            transaction.set_rollback(True)
