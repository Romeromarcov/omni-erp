"""
Valida un ConectorInstancia de Odoo contra el servidor real (Plan D — Fase D2).

Hace dos cosas, sin escribir nada en Odoo ni en Omni:
  1. test_connection() — conectividad + versión + permisos de lectura.
  2. pull_cartera_vencida() — una muestra acotada de la cartera vencida real,
     para confirmar que OdooCarteraProvider trae datos del Odoo de Lubrikca.

Nunca imprime credenciales (R-CODE-8). Es la herramienta que el proveedor corre
con las credenciales reales para cerrar el DoD de D2 (validación contra Odoo real).

Uso:
    python manage.py validar_conector_odoo --empresa <id_o_rif> [--limite 5]
    python manage.py validar_conector_odoo --instancia <id_conector> [--limite 5]
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Valida la conexión Odoo y una muestra de cartera vencida real (D2)."

    def add_arguments(self, parser):
        parser.add_argument("--empresa", help="id_empresa (UUID) o RIF del tenant.")
        parser.add_argument("--instancia", help="id_conector (UUID) de la instancia Odoo.")
        parser.add_argument("--limite", type=int, default=5, help="Máx. de partidas a mostrar.")

    def handle(self, *args, **opts):
        from apps.integration_hub.connectors.registry import registry
        from apps.integration_hub.models import ConectorInstancia

        instancia = self._resolver_instancia(ConectorInstancia, opts)

        self.stdout.write(f"Instancia: {instancia.nombre} (empresa={instancia.id_empresa_id})")
        connector = registry.get_connector(instancia)

        # 1) Conectividad
        resultado = connector.test_connection()
        if not resultado.success:
            raise CommandError(f"Conexión FALLÓ: {resultado.message}")
        self.stdout.write(self.style.SUCCESS(f"✔ Conexión OK — {resultado.message}"))

        # 2) Muestra de cartera vencida
        try:
            partidas = connector.pull_cartera_vencida(solo_vencidas=True)
        except Exception as exc:  # noqa: BLE001 — herramienta de diagnóstico
            raise CommandError(f"pull_cartera_vencida falló: {type(exc).__name__}: {exc}")

        total = len(partidas)
        self.stdout.write(self.style.SUCCESS(f"✔ Cartera vencida: {total} partidas."))
        for p in partidas[: opts["limite"]]:
            cliente = p.get("cliente_nombre", "—")
            monto = p.get("monto_pendiente", p.get("monto_total", "?"))
            bucket = p.get("bucket", "?")
            ref = p.get("orden_ref", "")
            self.stdout.write(f"  - {cliente}: {monto} [{bucket}] {ref}")

        if total == 0:
            self.stdout.write(self.style.WARNING(
                "Sin cartera vencida en Odoo (puede ser correcto). Conectividad validada."
            ))

    def _resolver_instancia(self, ConectorInstancia, opts):
        if opts.get("instancia"):
            try:
                return ConectorInstancia.objects.select_related("id_proveedor", "id_empresa").get(pk=opts["instancia"])
            except ConectorInstancia.DoesNotExist:
                raise CommandError(f"No existe instancia con id '{opts['instancia']}'.")

        if not opts.get("empresa"):
            raise CommandError("Indica --empresa o --instancia.")

        from apps.core.models import Empresa
        from django.core.exceptions import ValidationError

        try:
            empresa = Empresa.objects.get(pk=opts["empresa"])
        except (Empresa.DoesNotExist, ValidationError, ValueError):
            empresa = Empresa.objects.filter(identificador_fiscal=opts["empresa"]).first()
            if empresa is None:
                raise CommandError(f"No se encontró empresa con id o RIF '{opts['empresa']}'.")

        instancia = (
            ConectorInstancia.objects
            .select_related("id_proveedor", "id_empresa")
            .filter(id_empresa=empresa, id_proveedor__codigo="odoo", activo=True)
            .order_by("-fecha_actualizacion")
            .first()
        )
        if instancia is None:
            raise CommandError(
                f"La empresa {empresa.pk} no tiene un conector Odoo activo. "
                "Córre primero configurar_conector_odoo."
            )
        return instancia
