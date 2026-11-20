from decimal import Decimal

from apps.core.base_models import OmniBaseModel
from apps.core.uuid import uuid7

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
