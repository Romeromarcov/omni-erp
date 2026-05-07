from django.db import models
import uuid


class CostoProduccion(models.Model):
    id_costo_produccion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='costos_produccion')
    id_orden_produccion = models.ForeignKey('manufactura.OrdenProduccion', on_delete=models.CASCADE, related_name='costos')
    tipo_costo = models.CharField(max_length=20, choices=[
        ('MATERIAL_DIRECTO', 'Material Directo'),
        ('MANO_OBRA_DIRECTA', 'Mano de Obra Directa'),
        ('COSTOS_INDIRECTOS', 'Costos Indirectos'),
        ('OVERHEAD', 'Overhead')
    ])
    costo_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    costo_total = models.DecimalField(max_digits=18, decimal_places=4)
    id_moneda = models.ForeignKey('finanzas.Moneda', on_delete=models.CASCADE, related_name='costos_produccion')
    fecha_calculo = models.DateTimeField()
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'costos_costo_produccion'
        verbose_name = 'Costo de Producción'
        verbose_name_plural = 'Costos de Producción'

    def __str__(self):
        return f"OP-{self.id_orden_produccion.id} - {self.tipo_costo}: {self.costo_total}"


class CostoEstandarProducto(models.Model):
    id_costo_estandar = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='costos_estandar')
    id_producto = models.ForeignKey('inventario.Producto', on_delete=models.CASCADE, related_name='costos_estandar')
    tipo_costo = models.CharField(max_length=20, choices=[
        ('MATERIAL_DIRECTO', 'Material Directo'),
        ('MANO_OBRA_DIRECTA', 'Mano de Obra Directa'),
        ('COSTOS_INDIRECTOS', 'Costos Indirectos'),
        ('OVERHEAD', 'Overhead')
    ])
    costo_unitario_estandar = models.DecimalField(max_digits=18, decimal_places=4)
    id_moneda = models.ForeignKey('finanzas.Moneda', on_delete=models.CASCADE, related_name='costos_estandar')
    fecha_vigencia_desde = models.DateField()
    fecha_vigencia_hasta = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'costos_costo_estandar_producto'
        verbose_name = 'Costo Estándar de Producto'
        verbose_name_plural = 'Costos Estándar de Productos'

    def __str__(self):
        return f"{self.id_producto.nombre_producto} - {self.tipo_costo}: {self.costo_unitario_estandar}"


class AnalisisVariacionCosto(models.Model):
    id_analisis_variacion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='analisis_variacion_costos')
    id_orden_produccion = models.ForeignKey('manufactura.OrdenProduccion', on_delete=models.CASCADE, related_name='analisis_variacion')
    id_producto = models.ForeignKey('inventario.Producto', on_delete=models.CASCADE, related_name='analisis_variacion')
    tipo_costo = models.CharField(max_length=20, choices=[
        ('MATERIAL_DIRECTO', 'Material Directo'),
        ('MANO_OBRA_DIRECTA', 'Mano de Obra Directa'),
        ('COSTOS_INDIRECTOS', 'Costos Indirectos'),
        ('OVERHEAD', 'Overhead')
    ])
    costo_estandar = models.DecimalField(max_digits=18, decimal_places=4)
    costo_real = models.DecimalField(max_digits=18, decimal_places=4)
    variacion_cantidad = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    variacion_precio = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    variacion_total = models.DecimalField(max_digits=18, decimal_places=4)
    porcentaje_variacion = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    tipo_variacion = models.CharField(max_length=15, choices=[
        ('FAVORABLE', 'Favorable'),
        ('DESFAVORABLE', 'Desfavorable'),
        ('NEUTRO', 'Neutro')
    ])
    fecha_analisis = models.DateTimeField()
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'costos_analisis_variacion_costo'
        verbose_name = 'Análisis de Variación de Costo'
        verbose_name_plural = 'Análisis de Variaciones de Costos'

    def __str__(self):
        return f"OP-{self.id_orden_produccion.id} - {self.tipo_costo} - Variación: {self.variacion_total}"
