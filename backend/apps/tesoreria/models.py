from django.db import models

from apps.core.models import Empresa
from apps.finanzas.models import Moneda, Caja

class MovimientoInternoFondo(models.Model):
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    caja_origen = models.ForeignKey(Caja, on_delete=models.CASCADE, related_name='movimientos_salida')
    caja_destino = models.ForeignKey(Caja, on_delete=models.CASCADE, related_name='movimientos_entrada')
    id_moneda = models.ForeignKey(Moneda, on_delete=models.CASCADE, related_name='movimientos_internos', null=True, blank=True)
    id_banco_origen = models.ForeignKey('finanzas.CuentaBancariaEmpresa', on_delete=models.CASCADE, related_name='movimientos_banco_origen', null=True, blank=True)
    id_banco_destino = models.ForeignKey('finanzas.CuentaBancariaEmpresa', on_delete=models.CASCADE, related_name='movimientos_banco_destino', null=True, blank=True)
    usuario = models.ForeignKey('core.Usuarios', on_delete=models.CASCADE, related_name='movimientos_internos', null=True, blank=True)
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    fecha = models.DateTimeField(auto_now_add=True)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.caja_origen} -> {self.caja_destino}: {self.monto}"


class OperacionCambioDivisa(models.Model):
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='operaciones_cambio')
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    numero_operacion = models.CharField(max_length=50, unique=True)
    fecha_operacion = models.DateTimeField()
    tipo_operacion = models.CharField(max_length=20, choices=[
        ('COMPRA', 'Compra'),
        ('VENTA', 'Venta')
    ])
    moneda_origen = models.ForeignKey('finanzas.Moneda', on_delete=models.CASCADE, related_name='operaciones_origen')
    moneda_destino = models.ForeignKey('finanzas.Moneda', on_delete=models.CASCADE, related_name='operaciones_destino')
    monto_origen = models.DecimalField(max_digits=18, decimal_places=4)
    tasa_cambio = models.DecimalField(max_digits=18, decimal_places=6)
    monto_destino = models.DecimalField(max_digits=18, decimal_places=4)
    comision = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    caja_origen = models.ForeignKey('finanzas.Caja', on_delete=models.CASCADE, related_name='operaciones_cambio_origen', null=True, blank=True)
    caja_destino = models.ForeignKey('finanzas.Caja', on_delete=models.CASCADE, related_name='operaciones_cambio_destino', null=True, blank=True)
    banco_origen = models.ForeignKey('finanzas.CuentaBancariaEmpresa', on_delete=models.CASCADE, related_name='operaciones_cambio_banco_origen', null=True, blank=True)
    banco_destino = models.ForeignKey('finanzas.CuentaBancariaEmpresa', on_delete=models.CASCADE, related_name='operaciones_cambio_banco_destino', null=True, blank=True)
    referencia_transaccion_origen = models.CharField(max_length=100, null=True, blank=True)
    metodo_pago_origen = models.ForeignKey('finanzas.MetodoPago', on_delete=models.CASCADE, related_name='operaciones_cambio_metodo_origen', null=True, blank=True)
    referencia_transaccion_destino = models.CharField(max_length=100, null=True, blank=True)
    metodo_pago_destino = models.ForeignKey('finanzas.MetodoPago', on_delete=models.CASCADE, related_name='operaciones_cambio_metodo_destino', null=True, blank=True)
    casa_de_cambio = models.ForeignKey('proveedores.Proveedor', on_delete=models.SET_NULL, null=True, blank=True, related_name='operaciones_cambio')
    tipo_documento_gasto = models.CharField(max_length=50, null=True, blank=True)
    numero_documento_gasto = models.CharField(max_length=50, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tesoreria_operacion_cambio_divisa'
        verbose_name = 'Operación de Cambio de Divisa'
        verbose_name_plural = 'Operaciones de Cambio de Divisa'

    def __str__(self):
        return f"{self.numero_operacion} - {self.tipo_operacion}: {self.monto_origen} {self.moneda_origen} -> {self.monto_destino} {self.moneda_destino}"
