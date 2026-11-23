from decimal import Decimal

from apps.core.base_models import AMBITO_CONTABLE_CHOICES, OmniBaseModel
from apps.core.uuid import uuid7

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class OrdenCompra(models.Model):
    id_orden_compra = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    id_proveedor = models.ForeignKey("proveedores.Proveedor", on_delete=models.CASCADE)
    id_oferta_origen = models.ForeignKey(
        "OfertaProveedor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra_generadas",
    )
    id_almacen_destino = models.ForeignKey(
        "almacenes.Almacen",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra",
    )
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    tipo_operacion = models.CharField(max_length=50, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    numero_orden = models.CharField(max_length=50)
    fecha_orden = models.DateField()
    estado = models.CharField(
        max_length=30,
        choices=[
            ("BORRADOR", "Borrador"),
            ("ENVIADA", "Enviada"),
            ("APROBADA", "Aprobada"),
            ("RECHAZADA", "Rechazada"),
            ("CERRADA", "Cerrada"),
            ("ANULADA", "Anulada"),
        ],
        default="BORRADOR",
    )
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.numero_orden

    class Meta:
        db_table = "compras_orden_compra"
        verbose_name = "Orden de Compra"
        verbose_name_plural = "Órdenes de Compra"
        unique_together = [["id_empresa", "numero_orden"]]
        ordering = ["-fecha_orden"]


class DetalleOrdenCompra(models.Model):
    id_detalle_orden_compra = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_orden_compra = models.ForeignKey(OrdenCompra, related_name="detalles", on_delete=models.CASCADE)
    id_producto = models.ForeignKey("inventario.Producto", on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    observaciones = models.TextField(null=True, blank=True)


class RecepcionMercancia(models.Model):
    id_recepcion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="recepciones_mercancia")
    id_orden_compra = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name="recepciones")
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    fecha_recepcion = models.DateField()
    monto_total = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "compras_recepcion_mercancia"
        verbose_name = "Recepción de Mercancía"
        verbose_name_plural = "Recepciones de Mercancía"

    def __str__(self):
        return f"Recepción {self.id_recepcion!s:.8} — OC {self.id_orden_compra.numero_orden}"


class DetalleRecepcionMercancia(models.Model):
    ESTADO_CHOICES = [
        ("CONFORME", "Conforme"),
        ("DEFECTUOSO", "Defectuoso"),
        ("INCOMPLETO", "Incompleto"),
        ("DAÑADO", "Dañado"),
    ]

    id_detalle_recepcion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_recepcion = models.ForeignKey(RecepcionMercancia, on_delete=models.CASCADE, related_name="detalles")
    id_producto = models.ForeignKey("inventario.Producto", on_delete=models.CASCADE, related_name="detalles_recepcion")
    cantidad_esperada = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    cantidad_recibida = models.DecimalField(max_digits=18, decimal_places=4)
    costo_unitario = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    estado_mercancia = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="CONFORME")
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "compras_detalle_recepcion_mercancia"
        verbose_name = "Detalle de Recepción"
        verbose_name_plural = "Detalles de Recepción"

    def __str__(self):
        return f"{self.id_producto.nombre_producto} × {self.cantidad_recibida}"


class FacturaCompra(models.Model):
    id_factura_compra = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="facturas_compra")
    id_orden_compra = models.ForeignKey(
        OrdenCompra, on_delete=models.SET_NULL, null=True, blank=True, related_name="facturas"
    )
    id_proveedor = models.ForeignKey(
        "proveedores.Proveedor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facturas_compra",
    )
    id_recepcion = models.ForeignKey(
        RecepcionMercancia, on_delete=models.SET_NULL, null=True, blank=True, related_name="facturas"
    )
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    numero_factura = models.CharField(max_length=50)
    fecha_emision = models.DateField()
    monto_total = models.DecimalField(max_digits=18, decimal_places=4)
    ambito = models.CharField(
        max_length=12,
        choices=AMBITO_CONTABLE_CHOICES,
        default="FISCAL",
        db_index=True,
    )
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "compras_factura_compra"
        verbose_name = "Factura de Compra"
        verbose_name_plural = "Facturas de Compra"
        unique_together = [["id_empresa", "numero_factura"]]

    def __str__(self):
        return self.numero_factura


class RequisicionCompra(models.Model):
    id_requisicion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="requisiciones_compra")
    numero_requisicion = models.CharField(max_length=50)
    fecha_requisicion = models.DateField()
    id_solicitante = models.ForeignKey(
        "core.Usuarios", on_delete=models.CASCADE, related_name="requisiciones_solicitadas"
    )
    id_departamento = models.ForeignKey(
        "core.Departamento", on_delete=models.CASCADE, null=True, blank=True, related_name="requisiciones"
    )
    estado = models.CharField(
        max_length=20,
        choices=[
            ("BORRADOR", "Borrador"),
            ("PENDIENTE", "Pendiente"),
            ("APROBADA", "Aprobada"),
            ("RECHAZADA", "Rechazada"),
            ("PROCESADA", "Procesada"),
            ("ANULADA", "Anulada"),
        ],
        default="BORRADOR",
    )
    prioridad = models.CharField(
        max_length=15,
        choices=[("BAJA", "Baja"), ("MEDIA", "Media"), ("ALTA", "Alta"), ("URGENTE", "Urgente")],
        default="MEDIA",
    )
    fecha_necesidad = models.DateField()
    justificacion = models.TextField()
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "compras_requisicion_compra"
        verbose_name = "Requisición de Compra"
        verbose_name_plural = "Requisiciones de Compra"
        unique_together = [["id_empresa", "numero_requisicion"]]

    def __str__(self):
        return self.numero_requisicion


class DetalleRequisicionCompra(models.Model):
    id_detalle_requisicion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_requisicion = models.ForeignKey("RequisicionCompra", related_name="detalles", on_delete=models.CASCADE)
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.CASCADE, related_name="detalles_requisicion"
    )
    cantidad_solicitada = models.DecimalField(max_digits=18, decimal_places=4)
    precio_estimado = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    justificacion = models.TextField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "compras_detalle_requisicion_compra"
        verbose_name = "Detalle de Requisición"
        verbose_name_plural = "Detalles de Requisición"

    def __str__(self):
        return f"{self.id_requisicion.numero_requisicion} - {self.id_producto.nombre_producto}"


class SolicitudCotizacion(models.Model):
    id_solicitud_cotizacion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="solicitudes_cotizacion")
    numero_solicitud = models.CharField(max_length=50)
    fecha_solicitud = models.DateField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(
        max_length=20,
        choices=[
            ("BORRADOR", "Borrador"),
            ("ENVIADA", "Enviada"),
            ("RESPONDIDA", "Respondida"),
            ("VENCIDA", "Vencida"),
            ("ANULADA", "Anulada"),
        ],
        default="BORRADOR",
    )
    observaciones = models.TextField(null=True, blank=True)
    requisiciones = models.ManyToManyField(RequisicionCompra, blank=True, related_name="solicitudes_cotizacion")
    proveedores_invitados = models.ManyToManyField(
        "proveedores.Proveedor", blank=True, related_name="solicitudes_cotizacion"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "compras_solicitud_cotizacion"
        verbose_name = "Solicitud de Cotización"
        verbose_name_plural = "Solicitudes de Cotización"
        unique_together = [["id_empresa", "numero_solicitud"]]

    def __str__(self):
        return self.numero_solicitud


class DetalleSolicitudCotizacion(models.Model):
    id_detalle_solicitud = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_solicitud_cotizacion = models.ForeignKey(
        "SolicitudCotizacion", related_name="detalles", on_delete=models.CASCADE
    )
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.CASCADE, related_name="detalles_solicitud_cotizacion"
    )
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    especificaciones = models.TextField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "compras_detalle_solicitud_cotizacion"
        verbose_name = "Detalle de Solicitud de Cotización"
        verbose_name_plural = "Detalles de Solicitud de Cotización"

    def __str__(self):
        return f"{self.id_solicitud_cotizacion.numero_solicitud} - {self.id_producto.nombre_producto}"


class OfertaProveedor(models.Model):
    id_oferta = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_solicitud_cotizacion = models.ForeignKey(
        "SolicitudCotizacion", on_delete=models.CASCADE, related_name="ofertas"
    )
    id_proveedor = models.ForeignKey("proveedores.Proveedor", on_delete=models.CASCADE, related_name="ofertas")
    numero_oferta = models.CharField(max_length=50)
    fecha_oferta = models.DateField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(
        max_length=20,
        choices=[
            ("RECIBIDA", "Recibida"),
            ("EVALUADA", "Evaluada"),
            ("ACEPTADA", "Aceptada"),
            ("RECHAZADA", "Rechazada"),
            ("VENCIDA", "Vencida"),
        ],
        default="RECIBIDA",
    )
    monto_total = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    condiciones_pago = models.TextField(null=True, blank=True)
    tiempo_entrega = models.CharField(max_length=100, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "compras_oferta_proveedor"
        verbose_name = "Oferta de Proveedor"
        verbose_name_plural = "Ofertas de Proveedores"

    def __str__(self):
        return f"{self.numero_oferta} - {self.id_proveedor.razon_social}"


class DetalleOfertaProveedor(models.Model):
    id_detalle_oferta = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_oferta = models.ForeignKey("OfertaProveedor", related_name="detalles", on_delete=models.CASCADE)
    id_producto = models.ForeignKey("inventario.Producto", on_delete=models.CASCADE, related_name="detalles_oferta")
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    tiempo_entrega = models.CharField(max_length=100, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "compras_detalle_oferta_proveedor"
        verbose_name = "Detalle de Oferta"
        verbose_name_plural = "Detalles de Oferta"

    def __str__(self):
        return f"{self.id_oferta.numero_oferta} - {self.id_producto.nombre_producto}"


# DetalleRecepcionMercancia is defined earlier in this file (around line 74).
# The duplicate definition was removed; the canonical one above includes
# costo_unitario and subtotal (added via migration 0004).


class DetalleFacturaCompra(models.Model):
    id_detalle_factura = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_factura_compra = models.ForeignKey("FacturaCompra", related_name="detalles", on_delete=models.CASCADE)
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.CASCADE, related_name="detalles_factura_compra"
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
        db_table = "compras_detalle_factura_compra"
        verbose_name = "Detalle de Factura de Compra"
        verbose_name_plural = "Detalles de Factura de Compra"

    def __str__(self):
        return f"{self.id_factura_compra.numero_factura} - {self.id_producto.nombre_producto}"


# ── Costos en Destino / Landed Costs (Plan 09 Fase 5.1) ───────────────────────


class CostoDestino(OmniBaseModel):
    """Prorrateo de costos de importación/destino (flete, seguro, arancel, nacionalización)."""

    METODOS_PRORRATEO = [
        ("VALOR", "Por Valor (FOB / Compra)"),
        ("CANTIDAD", "Por Cantidad de Unidades"),
        ("PESO", "Por Peso (kg)"),
        ("VOLUMEN", "Por Volumen (m³)"),
    ]
    ESTADOS = [
        ("BORRADOR", "Borrador"),
        ("APLICADO", "Aplicado"),
        ("ANULADO", "Anulado"),
    ]

    id_costo_destino = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="costos_destino")
    id_recepcion = models.ForeignKey(RecepcionMercancia, on_delete=models.PROTECT, related_name="costos_destino")
    numero_documento = models.CharField(max_length=50)
    fecha = models.DateField()
    metodo_prorrateo = models.CharField(max_length=20, choices=METODOS_PRORRATEO, default="VALOR")
    ambito = models.CharField(
        max_length=12,
        choices=AMBITO_CONTABLE_CHOICES,
        default="FISCAL",
        db_index=True,
    )
    nro_expediente_impor = models.CharField(max_length=80, blank=True, default="")
    nro_planilla_impor = models.CharField(max_length=80, blank=True, default="")
    monto_total = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    estado = models.CharField(max_length=15, choices=ESTADOS, default="BORRADOR", db_index=True)
    id_asiento = models.ForeignKey(
        "contabilidad.AsientoContable",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="costos_destino",
    )
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        db_table = "compras_costo_destino"
        verbose_name = "Costo en Destino"
        verbose_name_plural = "Costos en Destino"
        unique_together = [["id_empresa", "numero_documento"]]
        ordering = ["-fecha", "-fecha_creacion"]
        constraints = [
            models.CheckConstraint(condition=Q(monto_total__gte=0), name="compras_costo_destino_total_gte_0"),
        ]

    def clean(self):
        super().clean()
        if self.id_recepcion_id and self.id_empresa_id and self.id_recepcion.id_empresa_id != self.id_empresa_id:
            raise ValidationError({"id_recepcion": "La recepción no pertenece a la empresa indicada."})

    def __str__(self):
        return f"{self.numero_documento} ({self.metodo_prorrateo}) [{self.estado}]"


class LineaCostoDestino(OmniBaseModel):
    """Concepto individual de costo en destino (flete, seguro, arancel, aduana, etc.)."""

    CONCEPTOS = [
        ("FLETE", "Flete Internacional / Nacional"),
        ("SEGURO", "Seguro de Carga"),
        ("ARANCEL", "Arancel / Derechos Aduanales"),
        ("NACIONALIZACION", "Gastos de Nacionalización / Agente Aduanal"),
        ("ALMACENAJE_ADUANA", "Almacenaje / Manejo Portuario"),
        ("OTRO", "Otro Costo en Destino"),
    ]

    id_linea_costo_destino = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="lineas_costo_destino")
    id_costo_destino = models.ForeignKey(CostoDestino, on_delete=models.CASCADE, related_name="lineas")
    concepto = models.CharField(max_length=25, choices=CONCEPTOS)
    descripcion = models.CharField(max_length=255)
    monto = models.DecimalField(max_digits=18, decimal_places=4)
    id_factura_compra = models.ForeignKey(
        FacturaCompra,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lineas_costo_destino",
    )
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        db_table = "compras_linea_costo_destino"
        verbose_name = "Línea de Costo en Destino"
        verbose_name_plural = "Líneas de Costo en Destino"
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="compras_linea_costo_destino_monto_gt_0"),
        ]

    def clean(self):
        super().clean()
        if (
            self.id_costo_destino_id
            and self.id_empresa_id
            and self.id_costo_destino.id_empresa_id != self.id_empresa_id
        ):
            raise ValidationError({"id_costo_destino": "El costo en destino no pertenece a la empresa indicada."})
        if (
            self.id_factura_compra_id
            and self.id_empresa_id
            and self.id_factura_compra.id_empresa_id != self.id_empresa_id
        ):
            raise ValidationError({"id_factura_compra": "La factura de compra no pertenece a la empresa indicada."})

    def __str__(self):
        return f"{self.concepto}: {self.monto}"


class AsignacionCostoDestino(OmniBaseModel):
    """Trazabilidad de prorrateo por línea de recepción y variación de costo unitario."""

    id_asignacion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="asignaciones_costo_destino")
    id_costo_destino = models.ForeignKey(CostoDestino, on_delete=models.CASCADE, related_name="asignaciones")
    id_detalle_recepcion = models.ForeignKey(
        DetalleRecepcionMercancia, on_delete=models.PROTECT, related_name="asignaciones_costo_destino"
    )
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.PROTECT, related_name="asignaciones_costo_destino"
    )
    base_prorrateo = models.DecimalField(max_digits=18, decimal_places=4)
    porcentaje_prorrateo = models.DecimalField(max_digits=8, decimal_places=4)
    costo_adicional_total = models.DecimalField(max_digits=18, decimal_places=4)
    costo_adicional_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    costo_unitario_anterior = models.DecimalField(max_digits=18, decimal_places=4)
    costo_unitario_nuevo = models.DecimalField(max_digits=18, decimal_places=4)

    class Meta:
        db_table = "compras_asignacion_costo_destino"
        verbose_name = "Asignación de Costo en Destino"
        verbose_name_plural = "Asignaciones de Costo en Destino"
        unique_together = [["id_costo_destino", "id_detalle_recepcion"]]
        constraints = [
            models.CheckConstraint(
                condition=Q(costo_adicional_total__gte=0), name="compras_asig_costo_dest_total_gte_0"
            ),
            models.CheckConstraint(
                condition=Q(costo_unitario_nuevo__gte=0), name="compras_asig_costo_dest_nuevo_gte_0"
            ),
        ]

    def __str__(self):
        return f"{self.id_producto.nombre_producto}: +{self.costo_adicional_unitario}/u"
