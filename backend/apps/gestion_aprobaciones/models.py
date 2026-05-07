from django.db import models
from apps.core.models import Empresa, Usuarios, Roles
import uuid

class TipoAprobacion(models.Model):
    id_tipo_aprobacion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    codigo_tipo = models.CharField(max_length=50, unique=True)
    nombre_tipo = models.CharField(max_length=100)
    descripcion = models.TextField(null=True, blank=True)
    modulo_origen = models.CharField(max_length=50)
    activo = models.BooleanField(default=True)

class FlujoAprobacion(models.Model):
    id_flujo_aprobacion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_tipo_aprobacion = models.ForeignKey(TipoAprobacion, on_delete=models.CASCADE)
    orden_etapa = models.IntegerField()
    nombre_etapa = models.CharField(max_length=100)
    rol_aprobador = models.ForeignKey(Roles, null=True, blank=True, on_delete=models.SET_NULL)
    id_usuario_aprobador = models.ForeignKey(Usuarios, null=True, blank=True, on_delete=models.SET_NULL)
    monto_minimo = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    monto_maximo = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    activo = models.BooleanField(default=True)

class SolicitudAprobacion(models.Model):
    id_solicitud_aprobacion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_tipo_aprobacion = models.ForeignKey(TipoAprobacion, on_delete=models.CASCADE)
    id_entidad_origen = models.UUIDField()
    nombre_modelo_origen = models.CharField(max_length=100)
    id_usuario_solicitante = models.ForeignKey(Usuarios, on_delete=models.CASCADE)
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    estado_solicitud = models.CharField(max_length=50)
    comentarios_solicitante = models.TextField(null=True, blank=True)
    fecha_ultima_actualizacion = models.DateTimeField(auto_now=True)
    etapa_actual_flujo = models.ForeignKey(FlujoAprobacion, null=True, blank=True, on_delete=models.SET_NULL)

class RegistroAprobacion(models.Model):
    id_registro_aprobacion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_solicitud_aprobacion = models.ForeignKey(SolicitudAprobacion, on_delete=models.CASCADE)
    id_flujo_aprobacion_etapa = models.ForeignKey(FlujoAprobacion, on_delete=models.CASCADE)
    id_usuario_aprobador = models.ForeignKey(Usuarios, on_delete=models.CASCADE)
    fecha_decision = models.DateTimeField(auto_now_add=True)
    tipo_decision = models.CharField(max_length=20)
    comentarios = models.TextField(null=True, blank=True)
