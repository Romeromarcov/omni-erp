from django.test import TestCase
from .models import ListaMateriales, RutaProduccion, OrdenProduccion, ConsumoMaterial, ProduccionTerminada

class ManufacturaTestCase(TestCase):
    def setUp(self):
        pass
    def test_modelos_manufactura(self):
        self.assertEqual(1, 1)
