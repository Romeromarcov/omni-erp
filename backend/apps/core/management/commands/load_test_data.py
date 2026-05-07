from django.core.management.base import BaseCommand
from apps.core.models import Empresa
from apps.finanzas.models import Moneda
from apps.inventario.models import Producto, CategoriaProducto, UnidadMedida

class Command(BaseCommand):
    help = 'Carga datos de prueba temporales para Empresas, Monedas y Productos'

    def handle(self, *args, **kwargs):
        # Monedas - Usar get_or_create para evitar duplicados
        usd, created = Moneda.objects.get_or_create(
            codigo_iso='USD',
            defaults={
                'nombre': 'Dólar',
                'simbolo': '$',
                'decimales': 2,
                'activo': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Moneda USD creada'))
        else:
            self.stdout.write(self.style.WARNING('Moneda USD ya existe'))

        eur, created = Moneda.objects.get_or_create(
            codigo_iso='EUR',
            defaults={
                'nombre': 'Euro',
                'simbolo': '€',
                'decimales': 2,
                'activo': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Moneda EUR creada'))
        else:
            self.stdout.write(self.style.WARNING('Moneda EUR ya existe'))

        # Empresas - Usar get_or_create para evitar duplicados
        acme, created = Empresa.objects.get_or_create(
            identificador_fiscal='123456789',
            defaults={
                'nombre_legal': 'Acme Corp',
                'nombre_comercial': 'Acme',
                'direccion_fiscal': 'Av. Principal 123',
                'telefono': '555-1234',
                'email_contacto': 'info@acme.com',
                'web_url': 'https://acme.com',
                'logo_url': 'https://acme.com/logo.png',
                'id_moneda_base': usd,
                'activo': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Empresa Acme creada'))
        else:
            self.stdout.write(self.style.WARNING('Empresa Acme ya existe'))

        globex, created = Empresa.objects.get_or_create(
            identificador_fiscal='987654321',
            defaults={
                'nombre_legal': 'Globex S.A.',
                'nombre_comercial': 'Globex',
                'direccion_fiscal': 'Calle Secundaria 456',
                'telefono': '555-5678',
                'email_contacto': 'contacto@globex.com',
                'web_url': 'https://globex.com',
                'logo_url': 'https://globex.com/logo.png',
                'id_moneda_base': eur,
                'activo': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Empresa Globex creada'))
        else:
            self.stdout.write(self.style.WARNING('Empresa Globex ya existe'))

        # Crear categorías de producto primero
        categoria_electronica, created = CategoriaProducto.objects.get_or_create(
            nombre_categoria='Electrónica',
            id_empresa=acme,
            defaults={
                'descripcion': 'Productos electrónicos y tecnológicos',
                'activo': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Categoría Electrónica creada'))
        else:
            self.stdout.write(self.style.WARNING('Categoría Electrónica ya existe'))

        categoria_muebles, created = CategoriaProducto.objects.get_or_create(
            nombre_categoria='Muebles',
            id_empresa=acme,
            defaults={
                'descripcion': 'Muebles y mobiliario',
                'activo': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Categoría Muebles creada'))
        else:
            self.stdout.write(self.style.WARNING('Categoría Muebles ya existe'))

        # Crear unidades de medida
        unidad_pieza, created = UnidadMedida.objects.get_or_create(
            abreviatura='PZA',
            defaults={
                'id_empresa': acme,
                'nombre': 'Pieza',
                'tipo': 'CANTIDAD',
                'activo': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Unidad de medida Pieza creada'))
        else:
            self.stdout.write(self.style.WARNING('Unidad de medida Pieza ya existe'))

        # Productos - Usar get_or_create para evitar duplicados
        laptop, created = Producto.objects.get_or_create(
            sku='LAPTOP-001',
            defaults={
                'id_empresa': acme,
                'nombre_producto': 'Laptop',
                'id_categoria': categoria_electronica,
                'id_unidad_medida_base': unidad_pieza,
                'descripcion': 'Laptop de alta gama',
                'tipo_producto': 'PRODUCTO_FISICO',
                'precio_venta_sugerido': 1200.00,
                'id_moneda_precio': usd,
                'activo': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Producto Laptop creado'))
        else:
            self.stdout.write(self.style.WARNING('Producto Laptop ya existe'))

        silla, created = Producto.objects.get_or_create(
            sku='SILLA-001',
            defaults={
                'id_empresa': acme,
                'nombre_producto': 'Silla',
                'id_categoria': categoria_muebles,
                'id_unidad_medida_base': unidad_pieza,
                'descripcion': 'Silla ergonómica de oficina',
                'tipo_producto': 'PRODUCTO_FISICO',
                'precio_venta_sugerido': 150.00,
                'id_moneda_precio': usd,
                'activo': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Producto Silla creado'))
        else:
            self.stdout.write(self.style.WARNING('Producto Silla ya existe'))

        self.stdout.write(self.style.SUCCESS('Proceso de carga de datos de prueba completado.'))
