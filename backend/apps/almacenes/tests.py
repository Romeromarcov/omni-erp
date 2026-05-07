from django.test import TestCase
from .models import Almacen
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.apps import apps

class AlmacenModelTest(TestCase):
    def setUp(self):
        Empresa = apps.get_model('core', 'Empresa')
        Sucursal = apps.get_model('core', 'Sucursal')
        self.empresa = Empresa.objects.create(nombre_legal='Empresa Test')
        self.sucursal = Sucursal.objects.create(nombre='Sucursal Test', id_empresa=self.empresa)

    def test_crear_almacen(self):
        almacen = Almacen.objects.create(
            id_empresa=self.empresa,
            nombre_almacen='Almacen Central',
            codigo_almacen='ALM001',
            direccion='Calle 1',
            id_sucursal=self.sucursal
        )
        self.assertEqual(almacen.nombre_almacen, 'Almacen Central')
        self.assertEqual(almacen.id_empresa, self.empresa)
        self.assertEqual(almacen.id_sucursal, self.sucursal)
