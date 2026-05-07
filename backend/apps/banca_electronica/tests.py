from django.test import TestCase
from .models import CuentaBancariaEmpresa

class BancaElectronicaTestCase(TestCase):
    def setUp(self):
        pass
    def test_modelos_banca(self):
        self.assertEqual(1, 1)
