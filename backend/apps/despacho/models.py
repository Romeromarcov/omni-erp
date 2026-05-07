from django.db import models
import uuid


class Despacho(models.Model):
    id_despacho = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='despachos')
    numero_despacho = models.CharField(max_length=50, unique=True)
    id_pedido = models.ForeignKey('ventas.Pedido', on_delete=models.CASCADE, related_name='despachos', null=True, blank=True)
    id_orden_compra = models.ForeignKey('compras.OrdenCompra', on_delete=models.CASCADE, related_name='despachos', null=True, blank=True)
    fecha_despacho = models.DateTimeField()
    id_almacen_origen = models.ForeignKey('almacenes.Almacen', on_delete=models.CASCADE, related_name='despachos_origen')
    direccion_destino = models.TextField()
    id_transportista = models.ForeignKey('rrhh.Empleado', on_delete=models.SET_NULL, null=True, blank=True, related_name='despachos_transportista')
    estado_despacho = models.CharField(max_length=20, choices=[
        ('PENDIENTE', 'Pendiente'),
        ('EN_PREPARACION', 'En Preparación'),
        ('LISTO_ENVIO', 'Listo para Envío'),
        ('EN_TRANSITO', 'En Tránsito'),
        ('ENTREGADO', 'Entregado'),
        ('DEVUELTO', 'Devuelto'),
        ('CANCELADO', 'Cancelado')
    ], default='PENDIENTE')
    fecha_entrega_estimada = models.DateTimeField(null=True, blank=True)
    fecha_entrega_real = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'despacho_despacho'
        verbose_name = 'Despacho'
        verbose_name_plural = 'Despachos'

    def __str__(self):
        return f"{self.numero_despacho} - {self.estado_despacho}"


class DetalleDespacho(models.Model):
    id_detalle_despacho = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_despacho = models.ForeignKey('Despacho', on_delete=models.CASCADE, related_name='detalles')
    id_producto = models.ForeignKey('inventario.Producto', on_delete=models.CASCADE, related_name='detalles_despacho')
    cantidad_despachada = models.DecimalField(max_digits=18, decimal_places=4)
    id_unidad_medida = models.ForeignKey('inventario.UnidadMedida', on_delete=models.CASCADE, related_name='detalles_despacho')
    lote = models.CharField(max_length=50, null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'despacho_detalle_despacho'
        verbose_name = 'Detalle de Despacho'
        verbose_name_plural = 'Detalles de Despacho'

    def __str__(self):
        return f"{self.id_despacho.numero_despacho} - {self.id_producto.nombre_producto} x {self.cantidad_despachada}"
