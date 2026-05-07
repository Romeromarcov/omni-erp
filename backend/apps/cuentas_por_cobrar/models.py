from django.db import models
from apps.crm.models import Cliente


class CuentaPorCobrar(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='cuentas_por_cobrar')
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField()
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, null=True, blank=True)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    tipo_operacion = models.CharField(max_length=50, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=[('pendiente', 'Pendiente'), ('pagada', 'Pagada'), ('vencida', 'Vencida'), ('parcial', 'Parcial')], default='pendiente')
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.cliente} - {self.monto} ({self.estado})"


# Modelo AbonoCxC movido aquí para evitar import circular
from apps.core.models import Usuarios

class AbonoCxC(models.Model):
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    cuenta_por_cobrar = models.ForeignKey(CuentaPorCobrar, on_delete=models.CASCADE, related_name='abonos')
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_abono = models.DateField(auto_now_add=True)
    usuario = models.ForeignKey(Usuarios, on_delete=models.SET_NULL, null=True, blank=True)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Abono de {self.monto} a {self.cuenta_por_cobrar}"
