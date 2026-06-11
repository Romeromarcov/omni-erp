"""
Ejecuta una exportación Odoo→Google Sheets para un tenant.

Lee de la instancia origen configurada en el conector de destino y vuelca las
entidades indicadas a la planilla de Google Sheets (upsert por fila).

Uso:
    python manage.py exportar_a_sheets \\
        --empresa <id_o_rif> \\
        --destino "Google Sheets Export"   # nombre de la instancia Sheets
        [--entidades contactos,productos] \\  # por defecto: entidades_activas
        [--full]                            # exportar todo (no incremental)
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Exporta entidades de un conector origen a Google Sheets."

    def add_arguments(self, parser):
        parser.add_argument("--empresa", required=True, help="id_empresa (UUID) o RIF.")
        parser.add_argument(
            "--destino", required=True, help="Nombre de la instancia Google Sheets."
        )
        parser.add_argument(
            "--entidades", default="", help="Lista separada por comas (opcional)."
        )
        parser.add_argument(
            "--full", action="store_true", help="Exportar todo (no incremental)."
        )

    def handle(self, *args, **opts):
        from apps.core.models import Empresa
        from apps.integration_hub.connectors.base import ConnectorError
        from apps.integration_hub.models import ConectorInstancia
        from apps.integration_hub.services.export_engine import ExportEngine

        empresa = self._resolver_empresa(Empresa, opts["empresa"])
        destino = ConectorInstancia.objects.filter(
            id_empresa=empresa, nombre=opts["destino"]
        ).first()
        if destino is None:
            raise CommandError(
                f"No se encontró la instancia de destino '{opts['destino']}' en la empresa."
            )

        tipos = [e.strip() for e in opts["entidades"].split(",") if e.strip()] or None

        try:
            jobs = ExportEngine().exportar(
                destino, tipos=tipos, incremental=not opts["full"]
            )
        except ConnectorError as exc:
            raise CommandError(str(exc))

        for job in jobs:
            estilo = (
                self.style.SUCCESS
                if job.estado.startswith("completado")
                else self.style.ERROR
            )
            self.stdout.write(
                estilo(
                    f"  {job.tipo_entidad}: {job.estado} — "
                    f"creados={job.creados} actualizados={job.actualizados} "
                    f"omitidos={job.omitidos} fallidos={job.fallidos}"
                )
            )
        self.stdout.write(
            self.style.SUCCESS(f"Exportación finalizada: {len(jobs)} entidad(es).")
        )

    def _resolver_empresa(self, Empresa, valor):
        from django.core.exceptions import ValidationError

        try:
            return Empresa.objects.get(pk=valor)
        except (Empresa.DoesNotExist, ValidationError, ValueError):
            empresa = Empresa.objects.filter(identificador_fiscal=valor).first()
            if empresa is None:
                raise CommandError(f"No se encontró empresa con id o RIF '{valor}'.")
            return empresa
