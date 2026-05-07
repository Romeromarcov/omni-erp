from django.db import models
from apps.core.models import Empresa, Usuarios
import uuid

class LogAuditoria(models.Model):
    id_log_auditoria = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    id_usuario = models.ForeignKey(Usuarios, null=True, blank=True, on_delete=models.SET_NULL)
    id_entidad_afectada = models.UUIDField(null=True, blank=True)
    nombre_entidad_afectada = models.CharField(max_length=100, null=True, blank=True)
    modulo = models.CharField(max_length=50)
    tipo_accion = models.CharField(max_length=50)
    descripcion_accion = models.TextField(null=True, blank=True)
    cambios_json = models.JSONField(null=True, blank=True)
    fecha_hora_accion = models.DateTimeField(auto_now_add=True)
    direccion_ip = models.GenericIPAddressField(null=True, blank=True)
    navegador_info = models.TextField(null=True, blank=True)
