import uuid
from apps.core.uuid import uuid7

from django.db import models

from apps.core.base_models import IntegrationFieldsMixin, OmniBaseModel, TimeStampedModel


class UnidadMedida(OmniBaseModel, IntegrationFieldsMixin):
    id_unidad_medida = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    nombre = models.CharField(max_length=50)
    abreviatura = models.CharField(max_length=10)
    tipo = models.CharField(
        max_length=50,
        choices=[("CANTIDAD", "Cantidad"), ("PESO", "Peso"), ("VOLUMEN", "Volumen"), ("LONGITUD", "Longitud")],
    )

    def __str__(self):
        return f"{self.nombre} ({self.abreviatura})"

    class Meta:
        db_table = "inventario_unidad_medida"
        verbose_name = "Unidad de Medida"
        verbose_name_plural = "Unidades de Medida"
        unique_together = [["id_empresa", "abreviatura"]]


class CategoriaProducto(OmniBaseModel, IntegrationFieldsMixin):
    id_categoria_producto = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    nombre_categoria = models.CharField(max_length=100)
    descripcion = models.TextField(null=True, blank=True)
    id_categoria_padre = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.nombre_categoria

    class Meta:
        db_table = "inventario_categoria_producto"
        verbose_name = "Categoría de Producto"
        verbose_name_plural = "Categorías de Producto"


class Producto(OmniBaseModel, IntegrationFieldsMixin):
    id_producto = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    tipo_operacion = models.CharField(max_length=50, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    nombre_producto = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, null=True, blank=True)
    id_categoria = models.ForeignKey(CategoriaProducto, on_delete=models.CASCADE)
    id_unidad_medida_base = models.ForeignKey(UnidadMedida, on_delete=models.CASCADE)
    descripcion = models.TextField(null=True, blank=True)
    tipo_producto = models.CharField(
        max_length=50,
        choices=[("PRODUCTO_FISICO", "Producto Físico"), ("SERVICIO", "Servicio"), ("KIT", "Kit"), ("COMBO", "Combo")],
        default="PRODUCTO_FISICO",
    )
    maneja_lotes = models.BooleanField(default=False)
    maneja_seriales = models.BooleanField(default=False)
    costo_promedio = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    precio_venta_sugerido = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    id_moneda_precio = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE)
    id_configuracion_impuesto_venta_default = models.ForeignKey(
        "fiscal.ConfiguracionImpuesto",
        null=True,
        blank=True,
        related_name="producto_impuesto_venta",
        on_delete=models.SET_NULL,
    )
    id_configuracion_impuesto_compra_default = models.ForeignKey(
        "fiscal.ConfiguracionImpuesto",
        null=True,
        blank=True,
        related_name="producto_impuesto_compra",
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return self.nombre_producto

    class Meta:
        db_table = "inventario_producto"
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        unique_together = [["id_empresa", "sku"]]
        indexes = [
            models.Index(fields=["id_empresa", "activo"]),
            models.Index(fields=["nombre_producto"]),
        ]


class VarianteProducto(OmniBaseModel):
    id_variante = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_producto = models.ForeignKey("Producto", on_delete=models.CASCADE, related_name="variantes")
    codigo_variante = models.CharField(max_length=50, null=True, blank=True)
    atributos_json = models.JSONField(default=dict)
    sku = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "inventario_variante_producto"
        verbose_name = "Variante de Producto"
        verbose_name_plural = "Variantes de Producto"

    def __str__(self):
        return f"{self.id_producto.nombre_producto} - {self.codigo_variante}"


class StockActual(models.Model):
    id_stock_actual = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    id_producto = models.ForeignKey("Producto", on_delete=models.CASCADE)
    id_variante = models.ForeignKey("VarianteProducto", on_delete=models.CASCADE, null=True, blank=True)
    id_almacen = models.ForeignKey("almacenes.Almacen", on_delete=models.CASCADE)
    cantidad_disponible = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    cantidad_comprometida = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    cantidad_en_transito = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    cantidad_minima = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    cantidad_maxima = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    fecha_ultima_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventario_stock_actual"
        verbose_name = "Stock Actual"
        verbose_name_plural = "Stocks Actuales"
        unique_together = [["id_producto", "id_variante", "id_almacen"]]

    def __str__(self):
        return f"{self.id_producto.nombre_producto} - {self.cantidad_disponible}"


class MovimientoInventario(TimeStampedModel):
    TIPOS_MOVIMIENTO = [
        ("ENTRADA", "Entrada"),
        ("SALIDA", "Salida"),
        ("TRANSFERENCIA", "Transferencia"),
        ("AJUSTE", "Ajuste"),
        ("CONSUMO_PRODUCCION", "Consumo Producción"),
        ("RECEPCION_COMPRA", "Recepción Compra"),
        ("DESPACHO_VENTA", "Despacho Venta"),
        ("SALIDA_INTERNA", "Salida Interna"),
        ("RESERVA_VENTA", "Reserva de Venta"),  # informativo — audit trail de confirmar_pedido()
    ]

    id_movimiento_inventario = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="movimientos_inventario")
    fecha_hora_movimiento = models.DateTimeField()
    tipo_movimiento = models.CharField(max_length=50, choices=TIPOS_MOVIMIENTO)
    id_producto = models.ForeignKey("Producto", on_delete=models.CASCADE, related_name="movimientos")
    id_variante = models.ForeignKey(
        "VarianteProducto", on_delete=models.CASCADE, related_name="movimientos", null=True, blank=True
    )
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    id_almacen_origen = models.ForeignKey(
        "almacenes.Almacen", on_delete=models.CASCADE, related_name="movimientos_origen", null=True, blank=True
    )
    id_almacen_destino = models.ForeignKey(
        "almacenes.Almacen", on_delete=models.CASCADE, related_name="movimientos_destino", null=True, blank=True
    )
    costo_unitario_movimiento = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    id_documento_origen = models.UUIDField(null=True, blank=True)
    nombre_modelo_origen = models.CharField(max_length=100, null=True, blank=True)
    id_usuario_registro = models.ForeignKey(
        "core.Usuarios", on_delete=models.CASCADE, related_name="movimientos_inventario_registrados"
    )
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "inventario_movimiento_inventario"
        verbose_name = "Movimiento de Inventario"
        verbose_name_plural = "Movimientos de Inventario"

    def __str__(self):
        return f"{self.tipo_movimiento} - {self.id_producto.nombre_producto}"

    @property
    def monto_total(self):
        """Valor contable del movimiento: |cantidad| × costo_unitario.
        Usado por generar_asiento() para extraer el monto del documento."""
        from decimal import Decimal
        if self.costo_unitario_movimiento:
            return abs(self.cantidad) * self.costo_unitario_movimiento
        return Decimal("0")


class ConversionUnidadMedida(OmniBaseModel):
    id_conversion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="conversiones_unidad")
    id_producto = models.ForeignKey("Producto", on_delete=models.CASCADE, related_name="conversiones_unidad")
    id_unidad_origen = models.ForeignKey("UnidadMedida", on_delete=models.CASCADE, related_name="conversiones_origen")
    id_unidad_destino = models.ForeignKey(
        "UnidadMedida", on_delete=models.CASCADE, related_name="conversiones_destino"
    )
    factor_conversion = models.DecimalField(max_digits=18, decimal_places=8)

    class Meta:
        db_table = "inventario_conversion_unidad_medida"
        verbose_name = "Conversión de Unidad de Medida"
        verbose_name_plural = "Conversiones de Unidades de Medida"
        unique_together = [["id_producto", "id_unidad_origen", "id_unidad_destino"]]

    def __str__(self):
        return f"{self.id_unidad_origen} -> {self.id_unidad_destino} (x{self.factor_conversion})"


class StockConsignacionCliente(TimeStampedModel):
    id_stock_consignacion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="stock_consignacion_clientes"
    )
    id_cliente = models.ForeignKey("crm.Cliente", on_delete=models.CASCADE, related_name="stock_consignacion")
    id_producto = models.ForeignKey("Producto", on_delete=models.CASCADE, related_name="stock_consignacion_clientes")
    id_variante = models.ForeignKey(
        "VarianteProducto", on_delete=models.CASCADE, related_name="stock_consignacion_clientes", null=True, blank=True
    )
    cantidad_consignada = models.DecimalField(max_digits=18, decimal_places=4)
    cantidad_vendida = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    cantidad_devuelta = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    fecha_consignacion = models.DateField()
    fecha_vencimiento = models.DateField(null=True, blank=True)
    precio_unitario_consignacion = models.DecimalField(max_digits=18, decimal_places=4)
    id_moneda = models.ForeignKey(
        "finanzas.Moneda", on_delete=models.CASCADE, related_name="stock_consignacion_clientes"
    )
    estado = models.CharField(
        max_length=20,
        choices=[("ACTIVA", "Activa"), ("VENCIDA", "Vencida"), ("CERRADA", "Cerrada"), ("CANCELADA", "Cancelada")],
        default="ACTIVA",
    )

    class Meta:
        db_table = "inventario_stock_consignacion_cliente"
        verbose_name = "Stock en Consignación a Cliente"
        verbose_name_plural = "Stocks en Consignación a Clientes"

    def __str__(self):
        return f"Consignación {self.id_cliente} - {self.id_producto.nombre_producto}"


class StockConsignacionProveedor(TimeStampedModel):
    id_stock_consignacion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="stock_consignacion_proveedores"
    )
    id_proveedor = models.ForeignKey(
        "proveedores.Proveedor", on_delete=models.CASCADE, related_name="stock_consignacion"
    )
    id_producto = models.ForeignKey(
        "Producto", on_delete=models.CASCADE, related_name="stock_consignacion_proveedores"
    )
    id_variante = models.ForeignKey(
        "VarianteProducto",
        on_delete=models.CASCADE,
        related_name="stock_consignacion_proveedores",
        null=True,
        blank=True,
    )
    cantidad_recibida = models.DecimalField(max_digits=18, decimal_places=4)
    cantidad_consumida = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    cantidad_devuelta = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    fecha_recepcion = models.DateField()
    fecha_vencimiento = models.DateField(null=True, blank=True)
    costo_unitario_consignacion = models.DecimalField(max_digits=18, decimal_places=4)
    id_moneda = models.ForeignKey(
        "finanzas.Moneda", on_delete=models.CASCADE, related_name="stock_consignacion_proveedores"
    )
    estado = models.CharField(
        max_length=20,
        choices=[("ACTIVA", "Activa"), ("VENCIDA", "Vencida"), ("CERRADA", "Cerrada"), ("CANCELADA", "Cancelada")],
        default="ACTIVA",
    )

    class Meta:
        db_table = "inventario_stock_consignacion_proveedor"
        verbose_name = "Stock en Consignación de Proveedor"
        verbose_name_plural = "Stocks en Consignación de Proveedores"

    def __str__(self):
        return f"Consignación {self.id_proveedor} - {self.id_producto.nombre_producto}"


# ── M5: Requisiciones Internas ────────────────────────────────────────────────


class RequisicionInterna(OmniBaseModel):
    ESTADOS = [
        ("BORRADOR", "Borrador"),
        ("APROBADA", "Aprobada"),
        ("DESPACHADA", "Despachada"),
        ("CANCELADA", "Cancelada"),
    ]

    id_requisicion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="requisiciones_internas")
    numero_requisicion = models.CharField(max_length=30)
    id_almacen_origen = models.ForeignKey(
        "almacenes.Almacen", on_delete=models.PROTECT, related_name="requisiciones_origen"
    )
    id_departamento_destino = models.ForeignKey(
        "core.Departamento", on_delete=models.SET_NULL, null=True, blank=True, related_name="requisiciones_recibidas"
    )
    solicitado_por = models.ForeignKey(
        "core.Usuarios", on_delete=models.PROTECT, related_name="requisiciones_internas_solicitadas"
    )
    aprobado_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requisiciones_internas_aprobadas",
    )
    estado = models.CharField(max_length=12, choices=ESTADOS, default="BORRADOR")
    fecha_solicitud = models.DateField(auto_now_add=True)
    fecha_aprobacion = models.DateField(null=True, blank=True)
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        db_table = "inventario_requisicion_interna"
        verbose_name = "Requisición Interna"
        verbose_name_plural = "Requisiciones Internas"
        unique_together = [["id_empresa", "numero_requisicion"]]

    def __str__(self):
        return f"REQ-{self.numero_requisicion} [{self.estado}]"


class DetalleRequisicion(models.Model):
    id_detalle = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_requisicion = models.ForeignKey(
        RequisicionInterna, on_delete=models.CASCADE, related_name="detalles"
    )
    id_producto = models.ForeignKey("Producto", on_delete=models.PROTECT, related_name="detalles_requisicion_interna")
    id_variante = models.ForeignKey(
        "VarianteProducto", on_delete=models.SET_NULL, null=True, blank=True
    )
    cantidad_solicitada = models.DecimalField(max_digits=18, decimal_places=4)
    cantidad_despachada = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        db_table = "inventario_detalle_requisicion"
        verbose_name = "Detalle de Requisición"
        verbose_name_plural = "Detalles de Requisición"
        unique_together = [["id_requisicion", "id_producto"]]

    def __str__(self):
        return f"{self.id_requisicion} | {self.id_producto.nombre_producto} x{self.cantidad_solicitada}"
