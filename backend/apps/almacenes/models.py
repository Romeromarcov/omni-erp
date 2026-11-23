from decimal import Decimal

from apps.core.base_models import AMBITO_CONTABLE_CHOICES, OmniBaseModel
from apps.core.uuid import uuid7

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class Almacen(models.Model):
    id_almacen = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    nombre_almacen = models.CharField(max_length=100)
    codigo_almacen = models.CharField(max_length=20)
    direccion = models.TextField(null=True, blank=True)
    id_sucursal = models.ForeignKey("core.Sucursal", null=True, blank=True, on_delete=models.SET_NULL)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    usa_ubicaciones = models.BooleanField(
        default=False,
        help_text="Si True, habilita control de stock y transferencias por ubicación interna (opt-in).",
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "almacenes_almacen"
        verbose_name = "Almacén"
        verbose_name_plural = "Almacenes"
        unique_together = [["id_empresa", "codigo_almacen"]]

    def __str__(self):
        return self.nombre_almacen


class UbicacionAlmacen(models.Model):
    TIPOS_UBICACION = [
        ("ESTANTERIA", "Estantería"),
        ("PISO", "Piso"),
        ("REFRIGERADO", "Refrigerado"),
        ("CONGELADO", "Congelado"),
        ("EXTERIOR", "Exterior"),
        ("CUARENTENA", "Cuarentena"),
        ("DEVOLUCION", "Devolución"),
        ("PICKING", "Picking"),
        ("RECEPCION", "Recepción"),
        ("DESPACHO", "Despacho"),
        ("TRANSITO", "Tránsito Inter-Almacén"),
    ]

    id_ubicacion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="ubicaciones_almacen")
    id_almacen = models.ForeignKey("Almacen", on_delete=models.CASCADE, related_name="ubicaciones")
    codigo_ubicacion = models.CharField(max_length=50)
    nombre_ubicacion = models.CharField(max_length=100)
    tipo_ubicacion = models.CharField(max_length=20, choices=TIPOS_UBICACION)
    pasillo = models.CharField(max_length=10, null=True, blank=True)
    estante = models.CharField(max_length=10, null=True, blank=True)
    nivel = models.CharField(max_length=10, null=True, blank=True)
    posicion = models.CharField(max_length=10, null=True, blank=True)
    capacidad_maxima = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    unidad_capacidad = models.CharField(max_length=20, null=True, blank=True)  # KG, M3, UNIDADES, etc.
    temperatura_minima = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    temperatura_maxima = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    activo = models.BooleanField(default=True)
    requiere_autorizacion = models.BooleanField(default=False)
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "almacenes_ubicacion_almacen"
        verbose_name = "Ubicación de Almacén"
        verbose_name_plural = "Ubicaciones de Almacén"
        unique_together = [["id_almacen", "codigo_ubicacion"]]

    def __str__(self):
        return f"{self.id_almacen.nombre_almacen} - {self.codigo_ubicacion}"


class StockUbicacion(OmniBaseModel):
    """Stock físico desagregado por ubicación dentro de un almacén con usa_ubicaciones=True."""

    id_stock_ubicacion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="stocks_ubicacion")
    id_almacen = models.ForeignKey("Almacen", on_delete=models.CASCADE, related_name="stocks_ubicacion")
    id_ubicacion = models.ForeignKey("UbicacionAlmacen", on_delete=models.CASCADE, related_name="stocks_ubicacion")
    id_producto = models.ForeignKey("inventario.Producto", on_delete=models.CASCADE, related_name="stocks_ubicacion")
    id_variante = models.ForeignKey(
        "inventario.VarianteProducto",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stocks_ubicacion",
    )
    cantidad_disponible = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    cantidad_reservada = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))

    class Meta:
        db_table = "almacenes_stock_ubicacion"
        verbose_name = "Stock por Ubicación"
        verbose_name_plural = "Stocks por Ubicación"
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "id_almacen", "id_ubicacion", "id_producto"],
                condition=Q(id_variante__isnull=True),
                name="alm_stock_ubic_unico_sin_var",
            ),
            models.UniqueConstraint(
                fields=["id_empresa", "id_almacen", "id_ubicacion", "id_producto", "id_variante"],
                condition=Q(id_variante__isnull=False),
                name="alm_stock_ubic_unico_con_var",
            ),
            models.CheckConstraint(condition=Q(cantidad_disponible__gte=0), name="alm_stock_ubic_disp_gte_0"),
            models.CheckConstraint(condition=Q(cantidad_reservada__gte=0), name="alm_stock_ubic_res_gte_0"),
            models.CheckConstraint(
                condition=Q(cantidad_reservada__lte=F("cantidad_disponible")),
                name="alm_stock_ubic_res_lte_disp",
            ),
        ]

    def __str__(self):
        return f"{self.id_ubicacion.codigo_ubicacion} | {self.id_producto.nombre_producto}: {self.cantidad_disponible}"


# ── Transferencia Inter-Almacén en Tránsito 2 Pasos (Plan 09 Fase 5.4) ──────


class TransferenciaTransito(OmniBaseModel):
    """Transferencia inter-almacén en 2 pasos (Despacho -> En Tránsito -> Recepción)."""

    ESTADOS = [
        ("EN_TRANSITO", "En Tránsito"),
        ("RECIBIDA", "Recibida"),
        ("CANCELADA", "Cancelada"),
    ]

    id_transferencia_transito = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="transferencias_transito")
    numero = models.CharField(max_length=50)
    id_almacen_origen = models.ForeignKey(
        Almacen, on_delete=models.PROTECT, related_name="transferencias_transito_salida"
    )
    id_almacen_destino = models.ForeignKey(
        Almacen, on_delete=models.PROTECT, related_name="transferencias_transito_entrada"
    )
    id_ubicacion_transito = models.ForeignKey(
        UbicacionAlmacen,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transferencias_transito",
    )
    ambito = models.CharField(
        max_length=12,
        choices=AMBITO_CONTABLE_CHOICES,
        default="FISCAL",
        db_index=True,
    )
    estado = models.CharField(max_length=15, choices=ESTADOS, default="EN_TRANSITO", db_index=True)
    fecha_despacho = models.DateTimeField()
    fecha_recepcion = models.DateTimeField(null=True, blank=True)
    id_usuario_despacho = models.ForeignKey(
        "core.Usuarios", on_delete=models.PROTECT, related_name="transferencias_transito_despachadas"
    )
    id_usuario_recepcion = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transferencias_transito_recibidas",
    )
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        db_table = "almacenes_transferencia_transito"
        verbose_name = "Transferencia en Tránsito"
        verbose_name_plural = "Transferencias en Tránsito"
        unique_together = [["id_empresa", "numero"]]
        ordering = ["-fecha_despacho", "-fecha_creacion"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(id_almacen_origen=F("id_almacen_destino")),
                name="alm_transito_origen_distinto_destino",
            ),
        ]

    def clean(self):
        super().clean()
        if self.id_almacen_origen_id == self.id_almacen_destino_id:
            raise ValidationError({"id_almacen_destino": "El almacén de origen y destino deben ser distintos."})
        if self.id_empresa_id:
            if self.id_almacen_origen_id and self.id_almacen_origen.id_empresa_id != self.id_empresa_id:
                raise ValidationError({"id_almacen_origen": "El almacén origen no pertenece a la empresa."})
            if self.id_almacen_destino_id and self.id_almacen_destino.id_empresa_id != self.id_empresa_id:
                raise ValidationError({"id_almacen_destino": "El almacén destino no pertenece a la empresa."})

    def __str__(self):
        return f"{self.numero} ({self.id_almacen_origen} -> {self.id_almacen_destino}) [{self.estado}]"


class DetalleTransferenciaTransito(OmniBaseModel):
    """Línea de producto de una TransferenciaTransito."""

    id_detalle = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="detalles_transferencia_transito"
    )
    id_transferencia = models.ForeignKey(TransferenciaTransito, on_delete=models.CASCADE, related_name="detalles")
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.PROTECT, related_name="detalles_transferencia_transito"
    )
    id_variante = models.ForeignKey(
        "inventario.VarianteProducto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detalles_transferencia_transito",
    )
    cantidad_despachada = models.DecimalField(max_digits=18, decimal_places=4)
    cantidad_recibida = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    costo_unitario = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))

    class Meta:
        db_table = "almacenes_detalle_transferencia_transito"
        verbose_name = "Detalle de Transferencia en Tránsito"
        verbose_name_plural = "Detalles de Transferencia en Tránsito"
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_despachada__gt=0), name="alm_det_transito_desp_gt_0"),
            models.CheckConstraint(condition=Q(cantidad_recibida__gte=0), name="alm_det_transito_rec_gte_0"),
        ]

    def __str__(self):
        return f"{self.id_transferencia.numero} | {self.id_producto.nombre_producto} x{self.cantidad_despachada}"
