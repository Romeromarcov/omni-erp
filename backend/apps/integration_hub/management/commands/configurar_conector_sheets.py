"""
Provisiona un ConectorInstancia de Google Sheets (destino de exportación).

El service account JSON se cifra en reposo (EncryptedJSONField, Fernet) y NUNCA
se imprime ni se loguea (R-CODE-8). El conector exporta a Sheets los datos que
lee de una instancia ORIGEN (p. ej. el conector Odoo de la misma empresa).

Uso:
    python manage.py configurar_conector_sheets \\
        --empresa <id_o_rif> \\
        --service-account /ruta/service_account.json \\
        --source "Odoo Lubrikca"        # nombre o id de la instancia origen
        [--nombre "Sheets Export"] \\
        [--folder <drive_folder_id>] \\   # carpeta de Drive donde crear la planilla
        [--spreadsheet-id <id>] \\        # usar una planilla existente
        [--titulo "Omni Export - Lubrikca"] \\
        [--entidades contactos,productos,facturas_venta] \\
        [--intervalo 60] \\
        [--test]                         # prueba la conexión tras crear
"""

import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = "Crea o actualiza un ConectorInstancia de Google Sheets para un tenant."

    def add_arguments(self, parser):
        parser.add_argument("--empresa", required=True, help="id_empresa (UUID) o RIF.")
        parser.add_argument(
            "--service-account",
            dest="service_account",
            required=True,
            help="Ruta al JSON de la cuenta de servicio de Google.",
        )
        parser.add_argument(
            "--source",
            required=True,
            help="Nombre o id de la instancia origen (de la que exportar).",
        )
        parser.add_argument("--nombre", default="Google Sheets Export")
        parser.add_argument(
            "--folder", default="", help="ID de carpeta de Drive (opcional)."
        )
        parser.add_argument("--spreadsheet-id", dest="spreadsheet_id", default="")
        parser.add_argument(
            "--titulo", default="", help="Título si se auto-crea la planilla."
        )
        parser.add_argument(
            "--entidades",
            default="contactos,productos",
            help="Lista separada por comas.",
        )
        parser.add_argument(
            "--intervalo",
            type=int,
            default=0,
            help="Minutos entre exports (0 = manual).",
        )
        parser.add_argument(
            "--test", action="store_true", help="Prueba la conexión tras crear."
        )

    def handle(self, *args, **opts):
        from apps.core.models import Empresa
        from apps.integration_hub.models import ConectorInstancia, ConectorProveedor

        empresa = self._resolver_empresa(Empresa, opts["empresa"])
        service_account = self._leer_service_account(opts["service_account"])
        proveedor = self._proveedor_sheets(ConectorProveedor)
        origen = self._resolver_origen(ConectorInstancia, empresa, opts["source"])
        entidades = [e.strip() for e in opts["entidades"].split(",") if e.strip()]

        configuracion = {
            "service_account": service_account,
            "source_instancia_id": str(origen.pk),
            "drive_folder_id": opts["folder"],
            "spreadsheet_id": opts["spreadsheet_id"],
            "titulo": opts["titulo"] or f"Omni Export - {empresa.nombre_legal}",
        }

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

        verbo = "creado" if creada else "actualizado"
        # NUNCA imprimir configuracion (contiene la clave del service account).
        self.stdout.write(
            self.style.SUCCESS(
                f"Conector Google Sheets {verbo}: {instancia.nombre} (empresa={empresa.pk}); "
                f"origen={origen.nombre}; entidades={entidades}; intervalo={opts['intervalo']}min."
            )
        )

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

    def _leer_service_account(self, ruta):
        if not os.path.exists(ruta):
            raise CommandError(f"No existe el archivo de service account: {ruta}")
        try:
            with open(ruta, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            raise CommandError(
                f"No se pudo leer el service account JSON: {type(exc).__name__}"
            )
        if "client_email" not in data:
            raise CommandError(
                "El JSON no parece un service account (falta 'client_email')."
            )
        return data

    def _proveedor_sheets(self, ConectorProveedor):
        proveedor, _ = ConectorProveedor.objects.get_or_create(
            codigo="google_sheets",
            defaults={
                "nombre": "Google Sheets",
                "descripcion": "Exporta datos canónicos a Google Sheets (cuenta de servicio).",
                "requiere_url": False,
                "requiere_db": False,
                "estado": "activo",
                "capacidades": [
                    "contactos",
                    "productos",
                    "pedidos_venta",
                    "pedidos_compra",
                    "facturas_venta",
                    "pagos",
                    "inventario",
                ],
            },
        )
        return proveedor

    def _resolver_origen(self, ConectorInstancia, empresa, valor):
        from django.core.exceptions import ValidationError

        origen = ConectorInstancia.objects.filter(
            id_empresa=empresa, nombre=valor
        ).first()
        if origen is None:
            # El pk es UUID: si 'valor' no es un UUID válido, el filtro lanza
            # ValidationError → lo tratamos como "no encontrado".
            try:
                origen = ConectorInstancia.objects.filter(
                    id_empresa=empresa, pk=valor
                ).first()
            except (ValidationError, ValueError):
                origen = None
        if origen is None:
            raise CommandError(
                f"No se encontró una instancia origen '{valor}' en la empresa "
                f"{empresa.pk}. Configúrala primero (p. ej. configurar_conector_odoo)."
            )
        return origen

    def _probar(self, instancia):
        from apps.integration_hub.connectors.registry import registry

        connector = registry.get_connector(instancia)
        resultado = connector.test_connection()
        instancia.ultimo_test_conexion = timezone.now()
        if resultado.success:
            instancia.estado = "activo"
            instancia.version_detectada = resultado.version or ""
            instancia.mensaje_estado = resultado.message
            instancia.save(
                update_fields=[
                    "estado",
                    "version_detectada",
                    "mensaje_estado",
                    "ultimo_test_conexion",
                ]
            )
            self.stdout.write(self.style.SUCCESS(f"  Test OK: {resultado.message}"))
        else:
            instancia.estado = "error"
            instancia.mensaje_estado = resultado.message
            instancia.save(
                update_fields=["estado", "mensaje_estado", "ultimo_test_conexion"]
            )
            self.stdout.write(self.style.ERROR(f"  Test FALLÓ: {resultado.message}"))
