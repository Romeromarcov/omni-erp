from django.db import models
import uuid

class Almacen(models.Model):
    id_almacen = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE)
    nombre_almacen = models.CharField(max_length=100)
    codigo_almacen = models.CharField(max_length=20, unique=True)
    direccion = models.TextField(null=True, blank=True)
    id_sucursal = models.ForeignKey('core.Sucursal', null=True, blank=True, on_delete=models.SET_NULL)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre_almacen


class UbicacionAlmacen(models.Model):
    TIPOS_UBICACION = [
        ('ESTANTERIA', 'Estantería'),
        ('PISO', 'Piso'),
        ('REFRIGERADO', 'Refrigerado'),
        ('CONGELADO', 'Congelado'),
        ('EXTERIOR', 'Exterior'),
        ('CUARENTENA', 'Cuarentena'),
        ('DEVOLUCION', 'Devolución'),
        ('PICKING', 'Picking'),
        ('RECEPCION', 'Recepción'),
        ('DESPACHO', 'Despacho'),
    ]

    id_ubicacion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='ubicaciones_almacen')
    id_almacen = models.ForeignKey('Almacen', on_delete=models.CASCADE, related_name='ubicaciones')
    codigo_ubicacion = models.CharField(max_length=50, unique=True)
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
        db_table = 'almacenes_ubicacion_almacen'
        verbose_name = 'Ubicación de Almacén'
        verbose_name_plural = 'Ubicaciones de Almacén'
        unique_together = ['id_almacen', 'codigo_ubicacion']

    def __str__(self):
        return f"{self.id_almacen.nombre_almacen} - {self.codigo_ubicacion}"
