from django.db import models
from apps.core.models import Empresa
from apps.finanzas.models import Moneda

class CuentaBancariaEmpresa(models.Model):
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='cuentas_bancarias')
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    banco = models.CharField(max_length=100)
    numero_cuenta = models.CharField(max_length=50, unique=True)
    tipo_cuenta = models.CharField(max_length=30, choices=[('corriente', 'Corriente'), ('ahorro', 'Ahorro')])
    moneda = models.ForeignKey(Moneda, on_delete=models.CASCADE)
    saldo_actual = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    activa = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.banco} - {self.numero_cuenta} ({self.empresa})"
