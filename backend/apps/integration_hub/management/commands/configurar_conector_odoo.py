"""
Provisiona un ConectorInstancia de Odoo para un tenant (Plan D — Fase D2).

Las credenciales se cifran en reposo (EncryptedJSONField, Fernet) — NUNCA se
imprimen ni se loguean (R-CODE-8). Pensado para configurar el Odoo real de
Lubrikca desde la consola del proveedor.

Uso:
    python manage.py configurar_conector_odoo \\
        --empresa <id_o_rif> \\
        --host https://lubrikca.odoo.com \\
        --db lubrikca \\
        --user api@lubrikca.com \\
        --api-key <clave>        # o vía env ODOO_API_KEY
        [--nombre "Odoo Lubrikca"] \\
        [--entidades pagos,contactos] \\
        [--intervalo 60] \\
        [--datasource-odoo] \\    # pone cxc.datasource=odoo para el tenant
        [--test]                  # prueba la conexión tras crear

Las credenciales pueden venir de variables de entorno si se omiten los flags:
    ODOO_HOST, ODOO_DB, ODOO_USER, ODOO_API_KEY
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = "Crea o actualiza un ConectorInstancia de Odoo para un tenant (D2)."

    def add_arguments(self, parser):
        parser.add_argument("--empresa", required=True, help="id_empresa (UUID) o identificador fiscal (RIF).")
        parser.add_argument("--host", default=os.environ.get("ODOO_HOST", ""))
        parser.add_argument("--db", default=os.environ.get("ODOO_DB", ""))
        parser.add_argument("--user", default=os.environ.get("ODOO_USER", ""))
        parser.add_argument("--api-key", dest="api_key", default=os.environ.get("ODOO_API_KEY", ""))
        parser.add_argument("--nombre", default="Odoo Lubrikca")
        parser.add_argument("--entidades", default="pagos", help="Lista separada por comas.")
        parser.add_argument("--intervalo", type=int, default=60, help="Minutos entre syncs (0 = manual).")
        parser.add_argument("--datasource-odoo", action="store_true",
                            help="Fija cxc.datasource=odoo para el tenant (la cartera se lee de Odoo).")
        parser.add_argument("--test", action="store_true", help="Prueba la conexión tras crear.")

    def handle(self, *args, **opts):
        from apps.core.models import Empresa
        from apps.integration_hub.models import ConectorInstancia, ConectorProveedor

        host, user, api_key = opts["host"], opts["user"], opts["api_key"]
        if not all([host, user, api_key]):
            raise CommandError(
                "Faltan credenciales. Provee --host, --user y --api-key "
                "(o las env ODOO_HOST/ODOO_USER/ODOO_API_KEY)."
            )

        empresa = self._resolver_empresa(Empresa, opts["empresa"])
        proveedor = self._proveedor_odoo(ConectorProveedor)
        entidades = [e.strip() for e in opts["entidades"].split(",") if e.strip()]

        configuracion = {"host": host, "db": opts["db"], "user": user, "api_key": api_key}

        with transaction.atomic():
            instancia, creada = ConectorInstancia.objects.update_or_create(
                id_empresa=empresa,
                nombre=opts["nombre"],
                defaults={
                    "id_proveedor": proveedor,
                    "configuracion": configuracion,
                    "estado": "configurando",
                    "intervalo_sync_minutos": opts["intervalo"],
                    "entidades_activas": entidades,
                    "activo": True,
                },
            )
            if opts["datasource_odoo"]:
                self._set_datasource_odoo(empresa)

        verbo = "creado" if creada else "actualizado"
        # NUNCA imprimir configuracion (contiene api_key).
        self.stdout.write(self.style.SUCCESS(
            f"Conector Odoo {verbo}: {instancia.nombre} (empresa={empresa.pk}); "
            f"entidades={entidades}; intervalo={opts['intervalo']}min."
        ))

        if opts["test"]:
            self._probar(instancia)

    def _resolver_empresa(self, Empresa, valor):
        from django.core.exceptions import ValidationError

        try:
            return Empresa.objects.get(pk=valor)
        except (Empresa.DoesNotExist, ValidationError, ValueError):
            empresa = Empresa.objects.filter(identificador_fiscal=valor).first()
            if empresa is None:
                raise CommandError(f"No se encontró empresa con id o RIF '{valor}'.")
            return empresa

    def _proveedor_odoo(self, ConectorProveedor):
        proveedor, _ = ConectorProveedor.objects.get_or_create(
            codigo="odoo",
            defaults={
                "nombre": "Odoo",
                "descripcion": "Conector Odoo (XML-RPC, v8–18+).",
                "requiere_url": True,
                "requiere_db": False,
                "estado": "activo",
                "capacidades": ["contactos", "productos", "pagos", "facturas_venta", "inventario"],
            },
        )
        return proveedor

    def _set_datasource_odoo(self, empresa):
        from apps.configuracion_motor.models import ParametroSistema

        ParametroSistema.objects.update_or_create(
            id_empresa=empresa,
            codigo_parametro="cxc.datasource",
            defaults={
                "nombre_parametro": "Fuente de datos de cartera CxC",
                "valor_parametro": "odoo",
                "tipo_dato": "TEXTO",
                "activo": True,
            },
        )
        self.stdout.write("  cxc.datasource = odoo (la cartera del tenant se lee de Odoo).")

    def _probar(self, instancia):
        from apps.integration_hub.connectors.registry import registry

        connector = registry.get_connector(instancia)
        resultado = connector.test_connection()
        instancia.ultimo_test_conexion = timezone.now()
        if resultado.success:
            instancia.estado = "activo"
            instancia.version_detectada = resultado.version or ""
            instancia.mensaje_estado = resultado.message
            instancia.save(update_fields=["estado", "version_detectada", "mensaje_estado", "ultimo_test_conexion"])
            self.stdout.write(self.style.SUCCESS(f"  Test OK: {resultado.message}"))
        else:
            instancia.estado = "error"
            instancia.mensaje_estado = resultado.message
            instancia.save(update_fields=["estado", "mensaje_estado", "ultimo_test_conexion"])
            self.stdout.write(self.style.ERROR(f"  Test FALLÓ: {resultado.message}"))
