from django.db import models
import uuid

class OrdenCompra(models.Model):
    id_orden_compra = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE)
    id_proveedor = models.ForeignKey('proveedores.Proveedor', on_delete=models.CASCADE)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    tipo_operacion = models.CharField(max_length=50, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    numero_orden = models.CharField(max_length=50)
    fecha_orden = models.DateField()
    estado = models.CharField(max_length=30, choices=[
        ('BORRADOR', 'Borrador'),
        ('ENVIADA', 'Enviada'),
        ('APROBADA', 'Aprobada'),
        ('RECHAZADA', 'Rechazada'),
        ('CERRADA', 'Cerrada'),
        ('ANULADA', 'Anulada')
    ], default='BORRADOR')
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.numero_orden

    class Meta:
        db_table = 'compras_orden_compra'
        verbose_name = 'Orden de Compra'
        verbose_name_plural = 'Órdenes de Compra'
        unique_together = [['id_empresa', 'numero_orden']]
        ordering = ['-fecha_orden']


class DetalleOrdenCompra(models.Model):
    id_detalle_orden_compra = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_orden_compra = models.ForeignKey(OrdenCompra, related_name='detalles', on_delete=models.CASCADE)
    id_producto = models.ForeignKey('inventario.Producto', on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    observaciones = models.TextField(null=True, blank=True)


class RecepcionMercancia(models.Model):
    id_recepcion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_orden_compra = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    fecha_recepcion = models.DateField()
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)


class FacturaCompra(models.Model):
    id_factura_compra = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_orden_compra = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    numero_factura = models.CharField(max_length=50)
    fecha_emision = models.DateField()
    monto_total = models.DecimalField(max_digits=18, decimal_places=4)
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.numero_factura


class RequisicionCompra(models.Model):
    id_requisicion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='requisiciones_compra')
    numero_requisicion = models.CharField(max_length=50)
    fecha_requisicion = models.DateField()
    id_solicitante = models.ForeignKey('core.Usuarios', on_delete=models.CASCADE, related_name='requisiciones_solicitadas')
    id_departamento = models.ForeignKey('core.Departamento', on_delete=models.CASCADE, null=True, blank=True, related_name='requisiciones')
    estado = models.CharField(max_length=20, choices=[
        ('BORRADOR', 'Borrador'),
        ('PENDIENTE', 'Pendiente'),
        ('APROBADA', 'Aprobada'),
        ('RECHAZADA', 'Rechazada'),
        ('PROCESADA', 'Procesada'),
        ('ANULADA', 'Anulada')
    ], default='BORRADOR')
    prioridad = models.CharField(max_length=15, choices=[
        ('BAJA', 'Baja'),
        ('MEDIA', 'Media'),
        ('ALTA', 'Alta'),
        ('URGENTE', 'Urgente')
    ], default='MEDIA')
    fecha_necesidad = models.DateField()
    justificacion = models.TextField()
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'compras_requisicion_compra'
        verbose_name = 'Requisición de Compra'
        verbose_name_plural = 'Requisiciones de Compra'
        unique_together = [['id_empresa', 'numero_requisicion']]

    def __str__(self):
        return self.numero_requisicion


class DetalleRequisicionCompra(models.Model):
    id_detalle_requisicion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_requisicion = models.ForeignKey('RequisicionCompra', related_name='detalles', on_delete=models.CASCADE)
    id_producto = models.ForeignKey('inventario.Producto', on_delete=models.CASCADE, related_name='detalles_requisicion')
    cantidad_solicitada = models.DecimalField(max_digits=18, decimal_places=4)
    precio_estimado = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    justificacion = models.TextField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'compras_detalle_requisicion_compra'
        verbose_name = 'Detalle de Requisición'
        verbose_name_plural = 'Detalles de Requisición'

    def __str__(self):
        return f"{self.id_requisicion.numero_requisicion} - {self.id_producto.nombre_producto}"


class SolicitudCotizacion(models.Model):
    id_solicitud_cotizacion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='solicitudes_cotizacion')
    numero_solicitud = models.CharField(max_length=50)
    fecha_solicitud = models.DateField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(max_length=20, choices=[
        ('BORRADOR', 'Borrador'),
        ('ENVIADA', 'Enviada'),
        ('RESPONDIDA', 'Respondida'),
        ('VENCIDA', 'Vencida'),
        ('ANULADA', 'Anulada')
    ], default='BORRADOR')
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'compras_solicitud_cotizacion'
        verbose_name = 'Solicitud de Cotización'
        verbose_name_plural = 'Solicitudes de Cotización'
        unique_together = [['id_empresa', 'numero_solicitud']]

    def __str__(self):
        return self.numero_solicitud


class DetalleSolicitudCotizacion(models.Model):
    id_detalle_solicitud = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_solicitud_cotizacion = models.ForeignKey('SolicitudCotizacion', related_name='detalles', on_delete=models.CASCADE)
    id_producto = models.ForeignKey('inventario.Producto', on_delete=models.CASCADE, related_name='detalles_solicitud_cotizacion')
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    especificaciones = models.TextField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'compras_detalle_solicitud_cotizacion'
        verbose_name = 'Detalle de Solicitud de Cotización'
        verbose_name_plural = 'Detalles de Solicitud de Cotización'

    def __str__(self):
        return f"{self.id_solicitud_cotizacion.numero_solicitud} - {self.id_producto.nombre_producto}"


class OfertaProveedor(models.Model):
    id_oferta = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_solicitud_cotizacion = models.ForeignKey('SolicitudCotizacion', on_delete=models.CASCADE, related_name='ofertas')
    id_proveedor = models.ForeignKey('proveedores.Proveedor', on_delete=models.CASCADE, related_name='ofertas')
    numero_oferta = models.CharField(max_length=50)
    fecha_oferta = models.DateField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(max_length=20, choices=[
        ('RECIBIDA', 'Recibida'),
        ('EVALUADA', 'Evaluada'),
        ('ACEPTADA', 'Aceptada'),
        ('RECHAZADA', 'Rechazada'),
        ('VENCIDA', 'Vencida')
    ], default='RECIBIDA')
    monto_total = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    condiciones_pago = models.TextField(null=True, blank=True)
    tiempo_entrega = models.CharField(max_length=100, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'compras_oferta_proveedor'
        verbose_name = 'Oferta de Proveedor'
        verbose_name_plural = 'Ofertas de Proveedores'

    def __str__(self):
        return f"{self.numero_oferta} - {self.id_proveedor.razon_social}"


class DetalleOfertaProveedor(models.Model):
    id_detalle_oferta = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_oferta = models.ForeignKey('OfertaProveedor', related_name='detalles', on_delete=models.CASCADE)
    id_producto = models.ForeignKey('inventario.Producto', on_delete=models.CASCADE, related_name='detalles_oferta')
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    tiempo_entrega = models.CharField(max_length=100, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'compras_detalle_oferta_proveedor'
        verbose_name = 'Detalle de Oferta'
        verbose_name_plural = 'Detalles de Oferta'

    def __str__(self):
        return f"{self.id_oferta.numero_oferta} - {self.id_producto.nombre_producto}"


class DetalleRecepcionMercancia(models.Model):
    id_detalle_recepcion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_recepcion = models.ForeignKey('RecepcionMercancia', related_name='detalles', on_delete=models.CASCADE)
    id_producto = models.ForeignKey('inventario.Producto', on_delete=models.CASCADE, related_name='detalles_recepcion')
    cantidad_esperada = models.DecimalField(max_digits=18, decimal_places=4)
    cantidad_recibida = models.DecimalField(max_digits=18, decimal_places=4)
    estado_mercancia = models.CharField(max_length=20, choices=[
        ('CONFORME', 'Conforme'),
        ('DEFECTUOSO', 'Defectuoso'),
        ('INCOMPLETO', 'Incompleto'),
        ('DAÑADO', 'Dañado')
    ], default='CONFORME')
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'compras_detalle_recepcion_mercancia'
        verbose_name = 'Detalle de Recepción'
        verbose_name_plural = 'Detalles de Recepción'

    def __str__(self):
        return f"{self.id_recepcion.id_recepcion} - {self.id_producto.nombre_producto}"


class DetalleFacturaCompra(models.Model):
    id_detalle_factura = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_factura_compra = models.ForeignKey('FacturaCompra', related_name='detalles', on_delete=models.CASCADE)
    id_producto = models.ForeignKey('inventario.Producto', on_delete=models.CASCADE, related_name='detalles_factura_compra')
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    descuento_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    descuento_monto = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    monto_impuesto = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    total_linea = models.DecimalField(max_digits=18, decimal_places=4)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'compras_detalle_factura_compra'
        verbose_name = 'Detalle de Factura de Compra'
        verbose_name_plural = 'Detalles de Factura de Compra'

    def __str__(self):
        return f"{self.id_factura_compra.numero_factura} - {self.id_producto.nombre_producto}"
