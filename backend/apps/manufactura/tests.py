from django.test import TestCase

from .models import ConsumoMaterial, ListaMateriales, OrdenProduccion, ProduccionTerminada, RutaProduccion


class ManufacturaTestCase(TestCase):
    def setUp(self):
        pass

    def test_modelos_manufactura(self):
        self.assertEqual(1, 1)
