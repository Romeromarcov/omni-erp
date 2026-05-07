from django.db import models
from apps.core.models import Empresa, Usuarios
import uuid

class PlantillaMigracion(models.Model):
    id_plantilla_migracion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre_plantilla = models.CharField(max_length=100)
    modulo_destino = models.CharField(max_length=50)
    modelo_destino = models.CharField(max_length=100)
    formato_archivo = models.CharField(max_length=20)
    estructura_json = models.JSONField()
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

class ProcesoMigracion(models.Model):
    id_proceso_migracion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    id_plantilla_migracion = models.ForeignKey(PlantillaMigracion, on_delete=models.CASCADE)
    id_usuario_ejecutor = models.ForeignKey(Usuarios, on_delete=models.CASCADE)
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    estado_proceso = models.CharField(max_length=50)
    total_registros_procesados = models.IntegerField(default=0)
    total_registros_exitosos = models.IntegerField(default=0)
    total_registros_fallidos = models.IntegerField(default=0)
    ruta_archivo_cargado = models.CharField(max_length=500)
    ruta_archivo_errores = models.CharField(max_length=500, null=True, blank=True)

class DetalleErrorMigracion(models.Model):
    id_detalle_error = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_proceso_migracion = models.ForeignKey(ProcesoMigracion, on_delete=models.CASCADE)
    numero_fila_archivo = models.IntegerField(null=True, blank=True)
    campo_error = models.CharField(max_length=100, null=True, blank=True)
    mensaje_error = models.TextField()
    datos_originales_json = models.JSONField(null=True, blank=True)
    fecha_registro_error = models.DateTimeField(auto_now_add=True)
