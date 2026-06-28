"""Sincroniza el espejo CxC Lubrikca desde Odoo (Fase 5, SOLO LECTURA).

Pobla las tablas-espejo del motor (pedidos, líneas, precios, pagos) y los
insumos de conciliación (monto_facturado / ncs_facturadas) leyendo del Odoo
activo de la empresa. Nunca escribe a Odoo ni a las tablas de trabajo humano.

Uso:
    python manage.py sincronizar_cxc_lubrikca --empresa <id_o_rif> [--desde "2026-06-01 00:00:00"]
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Sincroniza el espejo CxC Lubrikca desde Odoo (solo lectura)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--empresa", required=True, help="id_empresa (UUID) o RIF del tenant."
        )
        parser.add_argument(
            "--desde",
            default=None,
            help="Filtro delta opcional por write_date (ej. '2026-06-01 00:00:00').",
        )

    def handle(self, *args, **opts):
        from apps.core.models import Empresa
        from apps.cxc_lubrikca.services.sync import SyncError, sincronizar_empresa
        from django.core.exceptions import ValidationError

        empresa = self._resolver_empresa(Empresa, opts["empresa"], ValidationError)

        self.stdout.write(f"Sincronizando empresa {empresa.pk} desde Odoo…")
        try:
            counts = sincronizar_empresa(empresa, desde=opts.get("desde"))
        except SyncError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "✔ Sync OK — "
                f"pedidos={counts['pedidos']} líneas={counts['lineas']} "
                f"pagos={counts['pagos']} precios={counts['precios']} "
                f"facturas={counts['facturas']}"
            )
        )

    def _resolver_empresa(self, Empresa, valor, ValidationError):
        try:
            return Empresa.objects.get(pk=valor)
        except (Empresa.DoesNotExist, ValidationError, ValueError):
            empresa = Empresa.objects.filter(identificador_fiscal=valor).first()
            if empresa is None:
                raise CommandError(f"No se encontró empresa con id o RIF '{valor}'.")
            return empresa
