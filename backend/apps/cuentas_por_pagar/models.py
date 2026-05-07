from django.db import models
import uuid

class CuentaPorPagar(models.Model):
    id_cxp = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE)
    id_proveedor = models.ForeignKey('proveedores.Proveedor', on_delete=models.CASCADE)
    id_factura_compra = models.ForeignKey('compras.FacturaCompra', on_delete=models.CASCADE)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    tipo_operacion = models.CharField(max_length=50, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    monto_total = models.DecimalField(max_digits=18, decimal_places=4)
    monto_pendiente = models.DecimalField(max_digits=18, decimal_places=4)
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(max_length=30, choices=[
        ('PENDIENTE', 'Pendiente'),
        ('PAGADA', 'Pagada'),
        ('ANULADA', 'Anulada'),
        ('VENCIDA', 'Vencida'),
        ('PARCIAL', 'Parcial')
    ], default='PENDIENTE')
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"CxP {self.id_cxp}"


