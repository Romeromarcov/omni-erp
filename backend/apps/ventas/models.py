import uuid
from apps.core.uuid import uuid7

from django.db import models


class Pedido(models.Model):
    id_pedido = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    id_cliente = models.ForeignKey("crm.Cliente", on_delete=models.CASCADE)
    id_caja_fisica = models.ForeignKey(
        "finanzas.CajaFisica",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pedidos",
        help_text="Caja física donde se realizó el pedido.",
    )
    # Enlaces entre documentos
    id_cotizacion_origen = models.ForeignKey(
        "Cotizacion", on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos_derivados"
    )
    convertido_a_nota_venta = models.BooleanField(default=False)
    id_nota_venta_resultante = models.ForeignKey(
        "NotaVenta", on_delete=models.SET_NULL, null=True, blank=True, related_name="pedido_origen"
    )

    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    tipo_operacion = models.CharField(max_length=50, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    numero_pedido = models.CharField(max_length=50)
    fecha_pedido = models.DateField()
    estado = models.CharField(
        max_length=30,
        choices=[
            ("PENDIENTE", "Pendiente"),
            ("ENVIADO", "Enviado"),
            ("APROBADO", "Aprobado"),
            ("RECHAZADO", "Rechazado"),
            ("ANULADO", "Anulado"),
        ],
        default="PENDIENTE",
    )
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.numero_pedido

    class Meta:
        db_table = "ventas_pedido"
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ["-fecha_pedido"]
        unique_together = [["id_empresa", "numero_pedido"]]
        indexes = [
            models.Index(fields=["id_empresa", "estado"]),
            models.Index(fields=["fecha_pedido"]),
        ]


class DetallePedido(models.Model):
    id_detalle_pedido = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_pedido = models.ForeignKey(Pedido, related_name="detalles", on_delete=models.CASCADE)
    id_producto = models.ForeignKey("inventario.Producto", on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "ventas_detalle_pedido"
        verbose_name = "Detalle de Pedido"
        verbose_name_plural = "Detalles de Pedido"

    def __str__(self):
        return f"{self.id_pedido.numero_pedido} - {self.id_producto.nombre_producto}"


class NotaVenta(models.Model):
    id_nota_venta = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    id_cliente = models.ForeignKey("crm.Cliente", on_delete=models.CASCADE)
    # Enlaces entre documentos
    id_pedido_origen = models.ForeignKey(
        "Pedido", on_delete=models.SET_NULL, null=True, blank=True, related_name="notas_venta_derivadas"
    )
    convertido_a_factura = models.BooleanField(default=False)
    id_factura_resultante = models.ForeignKey(
        "FacturaFiscal", on_delete=models.SET_NULL, null=True, blank=True, related_name="nota_venta_origen"
    )

    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    numero_nota = models.CharField(max_length=50)
    fecha_nota = models.DateField()
    estado = models.CharField(
        max_length=30,
        choices=[
            ("BORRADOR", "Borrador"),
            ("ENTREGADA", "Entregada"),
            ("FACTURADA", "Facturada"),
            ("ANULADA", "Anulada"),
        ],
        default="BORRADOR",
    )
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.numero_nota

    class Meta:
        db_table = "ventas_nota_venta"
        verbose_name = "Nota de Venta"
        verbose_name_plural = "Notas de Venta"
        ordering = ["-fecha_nota"]
        unique_together = [["id_empresa", "numero_nota"]]
        indexes = [
            models.Index(fields=["id_empresa", "estado"]),
        ]


class DetalleNotaVenta(models.Model):
    id_detalle_nota_venta = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_nota_venta = models.ForeignKey(NotaVenta, related_name="detalles", on_delete=models.CASCADE)
    id_producto = models.ForeignKey("inventario.Producto", on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "ventas_detalle_nota_venta"
        verbose_name = "Detalle de Nota de Venta"
        verbose_name_plural = "Detalles de Nota de Venta"

    def __str__(self):
        return f"{self.id_nota_venta.numero_nota} - {self.id_producto.nombre_producto}"


class FacturaFiscal(models.Model):
    id_factura = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    id_cliente = models.ForeignKey("crm.Cliente", on_delete=models.CASCADE)
    # Enlaces entre documentos
    id_nota_venta_origen = models.ForeignKey(
        "NotaVenta", on_delete=models.SET_NULL, null=True, blank=True, related_name="facturas_derivadas"
    )

    # Campos fiscales específicos
    numero_control = models.CharField(
        max_length=50, help_text="Número de control compartido con notas de crédito"
    )
    numero_factura = models.CharField(max_length=50, help_text="Número individual de la factura")
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField(null=True, blank=True)

    # Montos
    base_imponible = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    monto_iva = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    monto_total = models.DecimalField(max_digits=18, decimal_places=4)

    # Moneda e impuestos
    id_moneda = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE, related_name="facturas_fiscales")
    tasa_cambio = models.DecimalField(max_digits=18, decimal_places=4, default=1.00)

    estado = models.CharField(
        max_length=20,
        choices=[
            ("BORRADOR", "Borrador"),
            ("EMITIDA", "Emitida"),
            ("VENCIDA", "Vencida"),
            ("PAGADA", "Pagada"),
            ("ANULADA", "Anulada"),
        ],
        default="BORRADOR",
    )

    # Control de inventario fiscal separado
    afecta_inventario_fiscal = models.BooleanField(default=True)

    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ventas_factura_fiscal"
        verbose_name = "Factura Fiscal"
        verbose_name_plural = "Facturas Fiscales"
        unique_together = [["id_empresa", "numero_factura"], ["id_empresa", "numero_control"]]

    def __str__(self):
        return f"{self.numero_factura} (Control: {self.numero_control})"


class Cotizacion(models.Model):
    id_cotizacion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="cotizaciones")
    id_cliente = models.ForeignKey("crm.Cliente", on_delete=models.CASCADE, related_name="cotizaciones")
    # Enlaces entre documentos
    id_cotizacion_origen = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="cotizaciones_derivadas"
    )
    convertido_a_pedido = models.BooleanField(default=False)
    id_pedido_resultante = models.ForeignKey(
        "Pedido", on_delete=models.SET_NULL, null=True, blank=True, related_name="cotizacion_origen"
    )

    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    numero_cotizacion = models.CharField(max_length=50)
    fecha_cotizacion = models.DateField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(
        max_length=30,
        choices=[
            ("BORRADOR", "Borrador"),
            ("ENVIADA", "Enviada"),
            ("ACEPTADA", "Aceptada"),
            ("RECHAZADA", "Rechazada"),
            ("VENCIDA", "Vencida"),
            ("ANULADA", "Anulada"),
        ],
        default="BORRADOR",
    )
    monto_total = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    id_moneda = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE, related_name="cotizaciones")
    observaciones = models.TextField(null=True, blank=True)
    condiciones_comerciales = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ventas_cotizacion"
        verbose_name = "Cotización"
        verbose_name_plural = "Cotizaciones"
        unique_together = [["id_empresa", "numero_cotizacion"]]

    def __str__(self):
        return self.numero_cotizacion


class DetalleCotizacion(models.Model):
    id_detalle_cotizacion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_cotizacion = models.ForeignKey("Cotizacion", related_name="detalles", on_delete=models.CASCADE)
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.CASCADE, related_name="detalles_cotizacion"
    )
    id_variante = models.ForeignKey(
        "inventario.VarianteProducto",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="detalles_cotizacion",
    )
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    descuento_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    descuento_monto = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "ventas_detalle_cotizacion"
        verbose_name = "Detalle de Cotización"
        verbose_name_plural = "Detalles de Cotización"

    def __str__(self):
        return f"{self.id_cotizacion.numero_cotizacion} - {self.id_producto.nombre_producto}"


class DetalleFacturaFiscal(models.Model):
    id_detalle_factura = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_factura = models.ForeignKey("FacturaFiscal", related_name="detalles", on_delete=models.CASCADE)
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.CASCADE, related_name="detalles_factura_fiscal"
    )
    id_variante = models.ForeignKey(
        "inventario.VarianteProducto",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="detalles_factura_fiscal",
    )
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    descuento_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    descuento_monto = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    monto_impuesto = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    total_linea = models.DecimalField(max_digits=18, decimal_places=4)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "ventas_detalle_factura_fiscal"
        verbose_name = "Detalle de Factura Fiscal"
        verbose_name_plural = "Detalles de Factura Fiscal"

    def __str__(self):
        return f"{self.id_factura.numero_factura} - {self.id_producto.nombre_producto}"


class NotaCreditoVenta(models.Model):
    id_nota_credito = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="notas_credito_venta")
    id_cliente = models.ForeignKey("crm.Cliente", on_delete=models.CASCADE, related_name="notas_credito")
    id_factura_origen = models.ForeignKey(
        "FacturaFiscal", on_delete=models.CASCADE, null=True, blank=True, related_name="notas_credito_venta"
    )
    numero_nota_credito = models.CharField(max_length=50)
    fecha_emision = models.DateField()
    motivo = models.CharField(
        max_length=20,
        choices=[
            ("DEVOLUCION", "Devolución"),
            ("DESCUENTO", "Descuento"),
            ("ERROR_FACTURACION", "Error de Facturación"),
            ("ANULACION", "Anulación"),
            ("OTRO", "Otro"),
        ],
    )
    monto_total = models.DecimalField(max_digits=18, decimal_places=4)
    id_moneda = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE, related_name="notas_credito_venta")
    estado = models.CharField(
        max_length=20,
        choices=[("BORRADOR", "Borrador"), ("EMITIDA", "Emitida"), ("APLICADA", "Aplicada"), ("ANULADA", "Anulada")],
        default="BORRADOR",
    )
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ventas_nota_credito_venta"
        verbose_name = "Nota de Crédito de Venta"
        verbose_name_plural = "Notas de Crédito de Venta"
        unique_together = [["id_empresa", "numero_nota_credito"]]

    def __str__(self):
        return self.numero_nota_credito


class DetalleNotaCreditoVenta(models.Model):
    id_detalle_nota_credito = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_nota_credito = models.ForeignKey("NotaCreditoVenta", related_name="detalles", on_delete=models.CASCADE)
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.CASCADE, related_name="detalles_nota_credito"
    )
    id_variante = models.ForeignKey(
        "inventario.VarianteProducto",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="detalles_nota_credito",
    )
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    monto_impuesto = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    total_linea = models.DecimalField(max_digits=18, decimal_places=4)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "ventas_detalle_nota_credito_venta"
        verbose_name = "Detalle de Nota de Crédito"
        verbose_name_plural = "Detalles de Nota de Crédito"

    def __str__(self):
        return f"{self.id_nota_credito.numero_nota_credito} - {self.id_producto.nombre_producto}"


class DevolucionVenta(models.Model):
    id_devolucion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="devoluciones_venta")
    id_cliente = models.ForeignKey("crm.Cliente", on_delete=models.CASCADE, related_name="devoluciones")
    id_factura_origen = models.ForeignKey(
        "FacturaFiscal", on_delete=models.CASCADE, null=True, blank=True, related_name="devoluciones"
    )
    # Nota de crédito generada automáticamente por la devolución
    id_nota_credito_generada = models.OneToOneField(
        "NotaCreditoVenta", on_delete=models.SET_NULL, null=True, blank=True, related_name="devolucion_origen"
    )

    numero_devolucion = models.CharField(max_length=50)
    fecha_devolucion = models.DateField()
    motivo_devolucion = models.CharField(
        max_length=20,
        choices=[
            ("DEFECTO", "Defecto"),
            ("GARANTIA", "Garantía"),
            ("ERROR_ENTREGA", "Error de Entrega"),
            ("CAMBIO_CLIENTE", "Cambio de Cliente"),
            ("VENCIMIENTO", "Vencimiento"),
            ("OTRO", "Otro"),
        ],
    )
    estado = models.CharField(
        max_length=20,
        choices=[
            ("PENDIENTE", "Pendiente"),
            ("APROBADA", "Aprobada"),
            ("PROCESADA", "Procesada"),
            ("RECHAZADA", "Rechazada"),
            ("ANULADA", "Anulada"),
        ],
        default="PENDIENTE",
    )
    monto_total = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    id_moneda = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE, related_name="devoluciones_venta")
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ventas_devolucion_venta"
        verbose_name = "Devolución de Venta"
        verbose_name_plural = "Devoluciones de Venta"
        unique_together = [["id_empresa", "numero_devolucion"]]

    def __str__(self):
        return self.numero_devolucion


class DetalleDevolucionVenta(models.Model):
    id_detalle_devolucion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_devolucion = models.ForeignKey("DevolucionVenta", related_name="detalles", on_delete=models.CASCADE)
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.CASCADE, related_name="detalles_devolucion"
    )
    id_variante = models.ForeignKey(
        "inventario.VarianteProducto",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="detalles_devolucion",
    )
    cantidad_devuelta = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    estado_producto = models.CharField(
        max_length=20,
        choices=[("BUENO", "Bueno"), ("DEFECTUOSO", "Defectuoso"), ("VENCIDO", "Vencido"), ("DAÑADO", "Dañado")],
    )
    accion_inventario = models.CharField(
        max_length=20,
        choices=[
            ("REINTEGRAR", "Reintegrar a Stock"),
            ("CUARENTENA", "Enviar a Cuarentena"),
            ("DESCARTAR", "Descartar"),
            ("REPARAR", "Enviar a Reparación"),
        ],
    )
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "ventas_detalle_devolucion_venta"
        verbose_name = "Detalle de Devolución"
        verbose_name_plural = "Detalles de Devolución"

    def __str__(self):
        return f"{self.id_devolucion.numero_devolucion} - {self.id_producto.nombre_producto}"


class NotaCreditoFiscal(models.Model):
    id_nota_credito_fiscal = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    id_cliente = models.ForeignKey("crm.Cliente", on_delete=models.CASCADE)

    # Enlaces fiscales - comparte número de control con la factura
    id_factura_origen = models.ForeignKey(
        "FacturaFiscal", on_delete=models.CASCADE, related_name="notas_credito_fiscal"
    )
    numero_control = models.CharField(max_length=50, help_text="Número de control compartido con la factura")
    numero_nota_credito = models.CharField(
        max_length=50, help_text="Número individual de la nota de crédito"
    )

    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField(null=True, blank=True)

    # Montos
    base_imponible = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    monto_iva = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    monto_total = models.DecimalField(max_digits=18, decimal_places=4)

    # Moneda e impuestos
    id_moneda = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE, related_name="notas_credito_fiscal")
    tasa_cambio = models.DecimalField(max_digits=18, decimal_places=4, default=1.00)

    # Motivo fiscal
    motivo = models.CharField(
        max_length=20,
        choices=[
            ("DEVOLUCION", "Devolución"),
            ("DESCUENTO", "Descuento"),
            ("ERROR_FACTURACION", "Error de Facturación"),
            ("ANULACION", "Anulación"),
            ("AJUSTE_PRECIO", "Ajuste de Precio"),
            ("OTRO", "Otro"),
        ],
    )

    # Estado fiscal
    estado = models.CharField(
        max_length=20,
        choices=[("BORRADOR", "Borrador"), ("EMITIDA", "Emitida"), ("APLICADA", "Aplicada"), ("ANULADA", "Anulada")],
        default="BORRADOR",
    )

    # Control de inventario fiscal separado
    afecta_inventario_fiscal = models.BooleanField(default=True)

    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ventas_nota_credito_fiscal"
        verbose_name = "Nota de Crédito Fiscal"
        verbose_name_plural = "Notas de Crédito Fiscal"
        unique_together = [["id_empresa", "numero_nota_credito"]]

    def __str__(self):
        return f"{self.numero_nota_credito} (Control: {self.numero_control})"


class DetalleNotaCreditoFiscal(models.Model):
    id_detalle_nota_credito = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_nota_credito_fiscal = models.ForeignKey("NotaCreditoFiscal", related_name="detalles", on_delete=models.CASCADE)
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.CASCADE, related_name="detalles_nota_credito_fiscal"
    )
    id_variante = models.ForeignKey(
        "inventario.VarianteProducto",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="detalles_nota_credito_fiscal",
    )
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    descuento_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    descuento_monto = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    monto_impuesto = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    total_linea = models.DecimalField(max_digits=18, decimal_places=4)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "ventas_detalle_nota_credito_fiscal"
        verbose_name = "Detalle de Nota de Crédito Fiscal"
        verbose_name_plural = "Detalles de Nota de Crédito Fiscal"

    def __str__(self):
        return f"{self.id_nota_credito_fiscal.numero_nota_credito} - {self.id_producto.nombre_producto}"


# ── Listas de Precios (M4) ────────────────────────────────────────────────────


class ListaPrecio(models.Model):
    """
    Lista de precios por empresa. Lista con es_referencia=True es la Lista 1 —
    siempre visible en documentos CxC como precio de referencia.
    """

    id_lista = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="listas_precio")
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, help_text="Código corto, ej: LISTA1, LISTA2, MAYOREO")
    es_referencia = models.BooleanField(
        default=False,
        help_text="Lista 1: precio base visible en todos los documentos CxC.",
    )
    id_moneda = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE, related_name="listas_precio")
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ventas_lista_precio"
        unique_together = [["id_empresa", "codigo"]]
        verbose_name = "Lista de Precios"
        verbose_name_plural = "Listas de Precios"

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"


class DetallePrecio(models.Model):
    """
    Precio de un producto en una lista. Soporta vigencia por fechas.
    """

    id_detalle = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_lista = models.ForeignKey(ListaPrecio, on_delete=models.CASCADE, related_name="detalles")
    id_producto = models.ForeignKey("inventario.Producto", on_delete=models.CASCADE, related_name="precios_lista")
    precio = models.DecimalField(max_digits=18, decimal_places=4)
    precio_minimo = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    vigente_desde = models.DateField(null=True, blank=True)
    vigente_hasta = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "ventas_detalle_precio"
        unique_together = [["id_lista", "id_producto"]]
        verbose_name = "Detalle de Precio"
        verbose_name_plural = "Detalles de Precio"

    def __str__(self):
        return f"{self.id_producto.nombre_producto} @ {self.id_lista.codigo}: {self.precio}"
