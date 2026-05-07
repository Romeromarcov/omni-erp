from django.test import TestCase
from .models import Caja, MovimientoInternoFondo

class TesoreriaTestCase(TestCase):
    def setUp(self):
        pass
    def test_modelos_tesoreria(self):
        self.assertEqual(1, 1)
