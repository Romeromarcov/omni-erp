from decimal import Decimal

from apps.core.uuid import uuid7

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.core.base_models import AMBITO_CONTABLE_CHOICES, IntegrationFieldsMixin, OmniBaseModel, TimeStampedModel


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
    estrategia_salida = models.CharField(
        max_length=10,
        choices=[("FIFO", "FIFO"), ("FEFO", "FEFO")],
        default="FIFO",
        help_text="Estrategia automática de descarga de lotes cuando maneja_lotes=True.",
    )
    # T10: producto solo-compra. Si es_vendible=False, el producto no puede
    # venderse (se bloquea al confirmar el pedido). es_comprable lo simétrico.
    es_vendible = models.BooleanField(
        default=True, help_text="Si es False, el producto es solo-compra y no puede venderse."
    )
    es_comprable = models.BooleanField(
        default=True, help_text="Si es False, el producto no puede comprarse (solo-venta)."
    )
    costo_promedio = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    costo_reposicion_usd = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Costo de reposición vigente en USD para cálculo de semáforo de margen real.",
    )
    margen_minimo_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("15.00"),
        help_text="Porcentaje de margen mínimo sobre costo de reposición; debajo dispara alerta ROJA.",
    )
    margen_alerta_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("25.00"),
        help_text="Porcentaje de margen preventivo; entre mínimo y alerta dispara semáforo AMARILLO.",
    )
    peso_unitario_kg = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    volumen_unitario_m3 = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    codigo_barras = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Código EAN/UPC/Code128 para escaneo rápido en conteos y Pick-Pack-Ship.",
    )
    metodo_valoracion = models.CharField(
        max_length=10,
        choices=[("PROMEDIO", "Costo Promedio"), ("FIFO", "FIFO (Primero en Entrar, Primero en Salir)")],
        default="PROMEDIO",
        help_text="Método de valoración de inventario usado al costear las salidas de este producto.",
    )
    precio_venta_sugerido = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    punto_reorden = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Stock mínimo a partir del cual se generan alertas de reorden. NULL = sin alerta.",
    )
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
        ("TRANSFERENCIA_UBICACION", "Transferencia entre Ubicaciones"),
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
    id_lote = models.ForeignKey(
        "LoteProducto", on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos"
    )
    ambito = models.CharField(
        max_length=12,
        choices=AMBITO_CONTABLE_CHOICES,
        default="FISCAL",
        db_index=True,
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
    id_requisicion = models.ForeignKey(RequisicionInterna, on_delete=models.CASCADE, related_name="detalles")
    id_producto = models.ForeignKey("Producto", on_delete=models.PROTECT, related_name="detalles_requisicion_interna")
    id_variante = models.ForeignKey("VarianteProducto", on_delete=models.SET_NULL, null=True, blank=True)
    cantidad_solicitada = models.DecimalField(max_digits=18, decimal_places=4)
    cantidad_despachada = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        db_table = "inventario_detalle_requisicion"
        verbose_name = "Detalle de Requisición"
        verbose_name_plural = "Detalles de Requisición"
        unique_together = [["id_requisicion", "id_producto"]]

    def __str__(self):
        return f"{self.id_requisicion} | {self.id_producto.nombre_producto} x{self.cantidad_solicitada}"


# ── Valoración de inventario (FIFO / Promedio) ────────────────────────────────


class ValoracionInventario(TimeStampedModel):
    """
    Registro de valoración por movimiento de inventario (FIFO / Promedio).

    Una fila por cada movimiento que afecta una pila de stock (empresa, producto,
    variante, almacén):

      - ``sentido == ENTRADA``: el movimiento crea una capa de costo. ``cantidad``
        y ``cantidad_restante`` arrancan iguales; ``cantidad_restante`` se va
        consumiendo conforme salen unidades (necesario para FIFO).
      - ``sentido == SALIDA``: el movimiento consume capas. ``costo_unitario`` es
        el costo de salida calculado (FIFO sobre las capas más antiguas, o
        promedio ponderado de las capas vivas). ``cantidad_restante`` es 0.

    ``valor_total`` = ``cantidad`` × ``costo_unitario`` y es la base del asiento
    contable (DR/CR inventario) de recepciones, despachos y ajustes.
    """

    SENTIDOS = [("ENTRADA", "Entrada"), ("SALIDA", "Salida")]
    METODOS = [("PROMEDIO", "Costo Promedio"), ("FIFO", "FIFO")]

    id_valoracion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="valoraciones_inventario")
    id_movimiento = models.ForeignKey("MovimientoInventario", on_delete=models.CASCADE, related_name="valoraciones")
    id_producto = models.ForeignKey("Producto", on_delete=models.CASCADE, related_name="valoraciones")
    id_variante = models.ForeignKey(
        "VarianteProducto", on_delete=models.CASCADE, related_name="valoraciones", null=True, blank=True
    )
    id_almacen = models.ForeignKey("almacenes.Almacen", on_delete=models.CASCADE, related_name="valoraciones")
    sentido = models.CharField(max_length=10, choices=SENTIDOS)
    metodo = models.CharField(max_length=10, choices=METODOS)
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    costo_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    valor_total = models.DecimalField(max_digits=18, decimal_places=4)
    cantidad_restante = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        help_text="Unidades de esta capa aún no consumidas (solo aplica a ENTRADA en FIFO).",
    )

    class Meta:
        db_table = "inventario_valoracion_inventario"
        verbose_name = "Valoración de Inventario"
        verbose_name_plural = "Valoraciones de Inventario"
        indexes = [
            models.Index(
                fields=["id_empresa", "id_producto", "id_variante", "id_almacen", "sentido"],
                name="inv_valoracion_pila_idx",
            ),
        ]

    def __str__(self):
        return f"{self.sentido} {self.cantidad} @ {self.costo_unitario} ({self.metodo})"


# ── Pasos de operación configurables por almacén (recepción / entrega) ────────


class PasoOperacion(OmniBaseModel):
    """
    Paso configurable de un flujo de operación de inventario, por almacén y tipo
    de operación. El tenant define la secuencia de pasos que una recepción o una
    entrega debe confirmar una a una antes de mover el stock.

    Ejemplos:
      RECEPCION: Confirmación → Calidad → Ubicación
      ENTREGA:   Picking → Empaque → Despacho → Entrega
    """

    TIPOS_OPERACION = [("RECEPCION", "Recepción"), ("ENTREGA", "Entrega")]

    id_paso_operacion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="pasos_operacion")
    id_almacen = models.ForeignKey("almacenes.Almacen", on_delete=models.CASCADE, related_name="pasos_operacion")
    tipo_operacion = models.CharField(max_length=12, choices=TIPOS_OPERACION)
    nombre_paso = models.CharField(max_length=100)
    secuencia = models.PositiveIntegerField(
        help_text="Orden del paso (1 = primero). Debe ser único por almacén y tipo de operación."
    )

    class Meta:
        db_table = "inventario_paso_operacion"
        verbose_name = "Paso de Operación"
        verbose_name_plural = "Pasos de Operación"
        ordering = ["id_almacen", "tipo_operacion", "secuencia"]
        unique_together = [
            ["id_almacen", "tipo_operacion", "secuencia"],
            ["id_almacen", "tipo_operacion", "nombre_paso"],
        ]

    def __str__(self):
        return f"{self.get_tipo_operacion_display()} · {self.secuencia}. {self.nombre_paso}"


# ── Operaciones de inventario con stepper (recepción / entrega) ───────────────


class OperacionInventario(OmniBaseModel):
    """
    Instancia de una operación de inventario (recepción o entrega) que avanza por
    los pasos configurados (PasoOperacion) del almacén. Al confirmar el último
    paso se mueve el stock físico y se generan valoración y asientos.

    El tipo de movimiento físico al completar se deriva de ``origen_tipo``:
      RECEPCION + PURCHASE   → RECEPCION_COMPRA (DR Inventario / CR CxP)
      ENTREGA   + SALE       → DESPACHO_VENTA   (COGS + ingresos en ventas)
      ENTREGA   + TRANSFER   → TRANSFERENCIA    (entre almacén origen y contraparte)
      ENTREGA   + RETURN/SCRAP → SALIDA
    """

    TIPOS_OPERACION = [("RECEPCION", "Recepción"), ("ENTREGA", "Entrega")]
    ORIGENES = [
        ("PURCHASE", "Compra"),
        ("SALE", "Venta"),
        ("TRANSFER", "Transferencia"),
        ("RETURN", "Devolución"),
        ("SCRAP", "Desecho"),
    ]
    ESTADOS = [
        ("EN_PROCESO", "En proceso"),
        ("COMPLETADA", "Completada"),
        ("CANCELADA", "Cancelada"),
    ]

    id_operacion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="operaciones_inventario")
    numero = models.CharField(max_length=30)
    tipo_operacion = models.CharField(max_length=12, choices=TIPOS_OPERACION)
    origen_tipo = models.CharField(max_length=12, choices=ORIGENES)
    origen_id = models.UUIDField(
        null=True, blank=True, help_text="Documento de origen (OC, NotaVenta, etc.) si aplica."
    )
    id_almacen = models.ForeignKey(
        "almacenes.Almacen",
        on_delete=models.PROTECT,
        related_name="operaciones_inventario",
        help_text="Almacén que recibe (recepción) o despacha (entrega).",
    )
    id_almacen_contraparte = models.ForeignKey(
        "almacenes.Almacen",
        on_delete=models.PROTECT,
        related_name="operaciones_inventario_contraparte",
        null=True,
        blank=True,
        help_text="Almacén destino en transferencias.",
    )
    estado = models.CharField(max_length=12, choices=ESTADOS, default="EN_PROCESO")
    motivo = models.TextField(blank=True, default="", help_text="Obligatorio para devoluciones/desechos.")
    fecha = models.DateTimeField()

    class Meta:
        db_table = "inventario_operacion_inventario"
        verbose_name = "Operación de Inventario"
        verbose_name_plural = "Operaciones de Inventario"
        unique_together = [["id_empresa", "numero"]]
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.get_tipo_operacion_display()} {self.numero} [{self.estado}]"


class OperacionInventarioPaso(models.Model):
    """Snapshot de un paso configurado, con su estado de confirmación en la operación."""

    id_operacion_paso = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_operacion = models.ForeignKey("OperacionInventario", on_delete=models.CASCADE, related_name="pasos")
    secuencia = models.PositiveIntegerField()
    nombre_paso = models.CharField(max_length=100)
    confirmado = models.BooleanField(default=False)
    id_usuario_confirmacion = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pasos_operacion_confirmados",
    )
    fecha_confirmacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "inventario_operacion_inventario_paso"
        verbose_name = "Paso de Operación de Inventario"
        verbose_name_plural = "Pasos de Operación de Inventario"
        ordering = ["secuencia"]
        unique_together = [["id_operacion", "secuencia"]]

    def __str__(self):
        marca = "✓" if self.confirmado else "·"
        return f"{marca} {self.secuencia}. {self.nombre_paso}"


class OperacionInventarioLinea(models.Model):
    """Línea de producto de una operación de inventario."""

    id_linea = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_operacion = models.ForeignKey("OperacionInventario", on_delete=models.CASCADE, related_name="lineas")
    id_producto = models.ForeignKey("Producto", on_delete=models.PROTECT, related_name="lineas_operacion")
    id_variante = models.ForeignKey("VarianteProducto", on_delete=models.SET_NULL, null=True, blank=True)
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    cantidad_escaneada = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        help_text="Cantidad verificada mediante escaneo de código de barras en Pick-Pack-Ship.",
    )
    costo_unitario = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Costo de recepción; en entregas lo calcula la valoración.",
    )

    class Meta:
        db_table = "inventario_operacion_inventario_linea"
        verbose_name = "Línea de Operación de Inventario"
        verbose_name_plural = "Líneas de Operación de Inventario"

    def __str__(self):
        return f"{self.id_producto.nombre_producto} x{self.cantidad}"


# ── Reabastecimiento automático y trazabilidad de lotes opt-in (Plan 08 §B.3) ─


class ReglaReabastecimiento(OmniBaseModel):
    """Regla de punto de reorden / stock máximo por (empresa, producto, variante, almacén)."""

    RUTAS = [
        ("COMPRA", "Compra"),
        ("MANUFACTURA", "Manufactura"),
        ("TRANSFERENCIA", "Transferencia"),
    ]

    id_regla = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="reglas_reabastecimiento")
    id_producto = models.ForeignKey("Producto", on_delete=models.CASCADE, related_name="reglas_reabastecimiento")
    id_variante = models.ForeignKey(
        "VarianteProducto",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reglas_reabastecimiento",
    )
    id_almacen = models.ForeignKey(
        "almacenes.Almacen", on_delete=models.CASCADE, related_name="reglas_reabastecimiento"
    )
    stock_minimo = models.DecimalField(max_digits=18, decimal_places=4)
    stock_maximo = models.DecimalField(max_digits=18, decimal_places=4)
    cantidad_multiplo = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("1"))
    ruta = models.CharField(max_length=20, choices=RUTAS, default="COMPRA")
    id_proveedor_preferido = models.ForeignKey(
        "proveedores.Proveedor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reglas_reabastecimiento",
    )
    id_almacen_origen = models.ForeignKey(
        "almacenes.Almacen",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reglas_reabastecimiento_origen",
    )

    class Meta:
        db_table = "inventario_regla_reabastecimiento"
        verbose_name = "Regla de Reabastecimiento"
        verbose_name_plural = "Reglas de Reabastecimiento"
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "id_producto", "id_almacen"],
                condition=Q(activo=True, id_variante__isnull=True),
                name="inv_regla_reabast_unica_sin_var",
            ),
            models.UniqueConstraint(
                fields=["id_empresa", "id_producto", "id_variante", "id_almacen"],
                condition=Q(activo=True, id_variante__isnull=False),
                name="inv_regla_reabast_unica_con_var",
            ),
            models.CheckConstraint(condition=Q(stock_minimo__gte=0), name="inv_regla_stock_min_gte_0"),
            models.CheckConstraint(
                condition=Q(stock_maximo__gte=F("stock_minimo")),
                name="inv_regla_stock_max_gte_min",
            ),
            models.CheckConstraint(condition=Q(cantidad_multiplo__gt=0), name="inv_regla_multiplo_gt_0"),
        ]

    def __str__(self):
        return f"{self.id_producto.nombre_producto} @ {self.id_almacen.nombre_almacen} [{self.ruta}]"


class LoteProducto(OmniBaseModel):
    """Lote trazable de producto por almacén (opt-in cuando Producto.maneja_lotes=True)."""

    id_lote = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="lotes_producto")
    id_producto = models.ForeignKey("Producto", on_delete=models.CASCADE, related_name="lotes")
    id_variante = models.ForeignKey(
        "VarianteProducto", on_delete=models.CASCADE, null=True, blank=True, related_name="lotes"
    )
    id_almacen = models.ForeignKey("almacenes.Almacen", on_delete=models.CASCADE, related_name="lotes_producto")
    numero_lote = models.CharField(max_length=80)
    fecha_fabricacion = models.DateField(null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True, db_index=True)
    cantidad_disponible = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    cantidad_reservada = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))

    class Meta:
        db_table = "inventario_lote_producto"
        verbose_name = "Lote de Producto"
        verbose_name_plural = "Lotes de Producto"
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "id_producto", "id_almacen", "numero_lote"],
                condition=Q(id_variante__isnull=True),
                name="inv_lote_unico_sin_var",
            ),
            models.UniqueConstraint(
                fields=["id_empresa", "id_producto", "id_variante", "id_almacen", "numero_lote"],
                condition=Q(id_variante__isnull=False),
                name="inv_lote_unico_con_var",
            ),
            models.CheckConstraint(condition=Q(cantidad_disponible__gte=0), name="inv_lote_disp_gte_0"),
            models.CheckConstraint(condition=Q(cantidad_reservada__gte=0), name="inv_lote_res_gte_0"),
            models.CheckConstraint(
                condition=Q(cantidad_reservada__lte=F("cantidad_disponible")),
                name="inv_lote_res_lte_disp",
            ),
        ]

    def __str__(self):
        return f"{self.numero_lote} ({self.id_producto.nombre_producto})"


class MovimientoLote(models.Model):
    """Detalle exacto de descarga o ingreso por lote asociado a un MovimientoInventario."""

    id_movimiento_lote = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_movimiento = models.ForeignKey(
        "MovimientoInventario", on_delete=models.CASCADE, related_name="movimientos_lote"
    )
    id_lote = models.ForeignKey("LoteProducto", on_delete=models.CASCADE, related_name="trazabilidad_movimientos")
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)

    class Meta:
        db_table = "inventario_movimiento_lote"
        verbose_name = "Movimiento por Lote"
        verbose_name_plural = "Movimientos por Lote"
        constraints = [
            models.CheckConstraint(condition=Q(cantidad__gt=0), name="inv_mov_lote_cantidad_gt_0"),
        ]

    def __str__(self):
        return f"{self.id_movimiento_id} -> {self.id_lote.numero_lote} x{self.cantidad}"


# ── Conteo Físico Cíclico / Total Dual (Plan 09 Fase 5.3) ─────────────────────


class ConteoInventario(OmniBaseModel):
    """Sesión de conteo físico cíclico/total con soporte dual FISCAL / GERENCIAL."""

    TIPOS = [
        ("CICLICO", "Conteo Cíclico"),
        ("TOTAL", "Inventario General / Total"),
        ("ALEATORIO", "Muestreo Aleatorio"),
    ]
    ESTADOS = [
        ("BORRADOR", "Borrador"),
        ("EN_PROGRESO", "En Progreso"),
        ("PENDIENTE_APROBACION", "Pendiente de Aprobación"),
        ("APLICADO", "Aplicado (Ajustado)"),
        ("ANULADO", "Anulado"),
    ]

    id_conteo = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="conteos_inventario")
    numero = models.CharField(max_length=50)
    id_almacen = models.ForeignKey("almacenes.Almacen", on_delete=models.PROTECT, related_name="conteos_inventario")
    ambito = models.CharField(
        max_length=12,
        choices=AMBITO_CONTABLE_CHOICES,
        default="FISCAL",
        db_index=True,
    )
    tipo_conteo = models.CharField(max_length=15, choices=TIPOS, default="CICLICO")
    estado = models.CharField(max_length=25, choices=ESTADOS, default="BORRADOR", db_index=True)
    fecha_conteo = models.DateField()
    id_responsable = models.ForeignKey(
        "core.Usuarios", on_delete=models.PROTECT, related_name="conteos_inventario_responsable"
    )
    id_aprobador = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conteos_inventario_aprobador",
    )
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        db_table = "inventario_conteo"
        verbose_name = "Conteo de Inventario"
        verbose_name_plural = "Conteos de Inventario"
        unique_together = [["id_empresa", "numero"]]
        ordering = ["-fecha_conteo", "-fecha_creacion"]

    def clean(self):
        super().clean()
        if self.id_almacen_id and self.id_empresa_id and self.id_almacen.id_empresa_id != self.id_empresa_id:
            raise ValidationError({"id_almacen": "El almacén no pertenece a la empresa indicada."})

    def __str__(self):
        return f"{self.numero} - {self.id_almacen.nombre_almacen} [{self.estado}]"


class LineaConteoInventario(OmniBaseModel):
    """Línea de conteo físico comparando existencia teórica vs contada por código de barras."""

    id_linea_conteo = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="lineas_conteo_inventario")
    id_conteo = models.ForeignKey(ConteoInventario, on_delete=models.CASCADE, related_name="lineas")
    id_producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="lineas_conteo")
    id_variante = models.ForeignKey(
        VarianteProducto, on_delete=models.SET_NULL, null=True, blank=True, related_name="lineas_conteo"
    )
    id_ubicacion = models.ForeignKey(
        "almacenes.UbicacionAlmacen",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lineas_conteo",
    )
    cantidad_sistema = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    cantidad_contada = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    diferencia = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    costo_unitario_referencia = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    valor_diferencia = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    conteos_escaneados = models.PositiveIntegerField(default=0)
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        db_table = "inventario_linea_conteo"
        verbose_name = "Línea de Conteo de Inventario"
        verbose_name_plural = "Líneas de Conteo de Inventario"
        constraints = [
            models.UniqueConstraint(
                fields=["id_conteo", "id_producto", "id_ubicacion"],
                condition=Q(id_variante__isnull=True),
                name="inv_linea_conteo_unica_sin_var",
            ),
            models.UniqueConstraint(
                fields=["id_conteo", "id_producto", "id_variante", "id_ubicacion"],
                condition=Q(id_variante__isnull=False),
                name="inv_linea_conteo_unica_con_var",
            ),
            models.CheckConstraint(
                condition=Q(cantidad_contada__isnull=True) | Q(cantidad_contada__gte=0),
                name="inv_linea_conteo_cant_gte_0",
            ),
        ]

    def clean(self):
        super().clean()
        if self.id_producto_id and self.id_empresa_id and self.id_producto.id_empresa_id != self.id_empresa_id:
            raise ValidationError({"id_producto": "El producto no pertenece a la empresa indicada."})
        if self.id_ubicacion_id and self.id_empresa_id and self.id_ubicacion.id_empresa_id != self.id_empresa_id:
            raise ValidationError({"id_ubicacion": "La ubicación no pertenece a la empresa indicada."})

    def __str__(self):
        return f"{self.id_conteo.numero} | {self.id_producto.nombre_producto}: dif={self.diferencia}"
