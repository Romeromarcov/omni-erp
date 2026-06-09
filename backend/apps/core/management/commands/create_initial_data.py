from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import Empresa, Usuarios


class Command(BaseCommand):
    help = (
        "[DEV ONLY · DEPRECATED] Crea datos demo (empresa 'Innova Systems' + admin/admin123). "
        "Para producción use 'seed_empresa_inicial' (parametrizable, sin password hardcodeada)."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        # Este comando crea un superusuario con contraseña DÉBIL y hardcodeada
        # (admin123). Es solo para bootstrap de desarrollo. En producción (DEBUG
        # False) se BLOQUEA: usar 'seed_empresa_inicial', que no incrusta secretos
        # (R-CODE-8) y valida la contraseña.
        if not settings.DEBUG:
            raise CommandError(
                "create_initial_data está deshabilitado fuera de DEBUG (crea un "
                "superusuario con contraseña hardcodeada 'admin123'). Para sembrar "
                "una empresa en producción use:\n"
                "    python manage.py seed_empresa_inicial --nombre-legal ... --rif ... "
                "--admin-username ... --admin-email ...\n"
                "(la contraseña se toma de --admin-password / OMNI_SEED_ADMIN_PASSWORD "
                "o se genera y valida)."
            )

        # 1. Crear la empresa por defecto si no existe
        empresa_nombre = "Innova Systems C.A."
        if not Empresa.objects.filter(nombre_legal=empresa_nombre).exists():
            self.stdout.write(f"Creando empresa por defecto: {empresa_nombre}")
            empresa = Empresa.objects.create(
                nombre_legal=empresa_nombre,
                nombre_comercial="Innova Systems",
                identificador_fiscal="J-12345678-9",
                email_contacto="admin@innovasystems.com",
                activo=True,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Empresa '{empresa.nombre_legal}' creada con éxito."
                )
            )
        else:
            empresa = Empresa.objects.get(nombre_legal=empresa_nombre)
            self.stdout.write(
                self.style.WARNING(f"La empresa '{empresa.nombre_legal}' ya existe.")
            )

        # 2. Crear el superusuario si no existe
        username = "admin"
        if not Usuarios.objects.filter(username=username).exists():
            self.stdout.write(f"Creando superusuario: {username}")
            admin_user = Usuarios.objects.create_superuser(
                username=username,
                email="admin@innovasystems.com",
                password="admin123",
                es_superusuario_omni=True,
            )
            # Usuarios.empresas es ManyToMany (no FK id_empresa): se asocia tras crear.
            admin_user.empresas.add(empresa)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Superusuario '{admin_user.username}' creado con éxito."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(f"El superusuario '{username}' ya existe.")
            )
