from django.db import models
from apps.core.models import Empresa
import uuid

class ConfiguracionIntegracion(models.Model):
    id_configuracion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    nombre_integracion = models.CharField(max_length=100)
    tipo_integracion = models.CharField(max_length=50)
    url_endpoint = models.URLField(null=True, blank=True)
    credenciales_json = models.JSONField(null=True, blank=True)
    formato_datos = models.CharField(max_length=50)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

class LogIntegracion(models.Model):
    id_log_integracion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_configuracion = models.ForeignKey(ConfiguracionIntegracion, on_delete=models.CASCADE)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    tipo_transaccion = models.CharField(max_length=50)
    id_entidad_origen = models.UUIDField(null=True, blank=True)
    nombre_modelo_origen = models.CharField(max_length=100, null=True, blank=True)
    request_payload_json = models.JSONField(null=True, blank=True)
    response_payload_json = models.JSONField(null=True, blank=True)
    estado_integracion = models.CharField(max_length=50)
    mensaje_error = models.TextField(null=True, blank=True)
    duracion_ms = models.IntegerField(null=True, blank=True)

class MapeoCampo(models.Model):
    id_mapeo_campo = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_configuracion_integracion = models.ForeignKey(ConfiguracionIntegracion, on_delete=models.CASCADE)
    nombre_campo_interno = models.CharField(max_length=100)
    nombre_campo_externo = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)
