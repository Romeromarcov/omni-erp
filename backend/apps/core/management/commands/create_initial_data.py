from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import Empresa, Usuarios

class Command(BaseCommand):
    help = 'Crea una empresa por defecto y un superusuario inicial.'

    @transaction.atomic
    def handle(self, *args, **options):
        # 1. Crear la empresa por defecto si no existe
        empresa_nombre = 'Innova Systems C.A.'
        if not Empresa.objects.filter(nombre_legal=empresa_nombre).exists():
            self.stdout.write(f"Creando empresa por defecto: {empresa_nombre}")
            empresa = Empresa.objects.create(
                nombre_legal=empresa_nombre,
                nombre_comercial='Innova Systems',
                identificador_fiscal='J-12345678-9',
                email_contacto='admin@innovasystems.com',
                activo=True
            )
            self.stdout.write(self.style.SUCCESS(f"Empresa '{empresa.nombre_legal}' creada con éxito."))
        else:
            empresa = Empresa.objects.get(nombre_legal=empresa_nombre)
            self.stdout.write(self.style.WARNING(f"La empresa '{empresa.nombre_legal}' ya existe."))

        # 2. Crear el superusuario si no existe
        username = 'admin'
        if not Usuarios.objects.filter(username=username).exists():
            self.stdout.write(f"Creando superusuario: {username}")
            admin_user = Usuarios.objects.create_superuser(
                username=username,
                email='admin@innovasystems.com',
                password='admin123',
                id_empresa=empresa,
                es_superusuario_omni=True
            )
            self.stdout.write(self.style.SUCCESS(f"Superusuario '{admin_user.username}' creado con éxito."))
        else:
            self.stdout.write(self.style.WARNING(f"El superusuario '{username}' ya existe."))
