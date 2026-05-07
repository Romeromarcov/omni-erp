from django.db import models
from apps.core.models import Empresa, Usuarios
import uuid

class Carpeta(models.Model):
    id_carpeta = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    nombre_carpeta = models.CharField(max_length=255)
    id_carpeta_padre = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    id_usuario_creacion = models.ForeignKey(Usuarios, on_delete=models.CASCADE)
    es_publica = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

class Documento(models.Model):
    id_documento = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    nombre_archivo = models.CharField(max_length=255)
    tipo_contenido = models.CharField(max_length=100)
    tamano_bytes = models.BigIntegerField()
    ruta_almacenamiento = models.CharField(max_length=500)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    id_usuario_subida = models.ForeignKey(Usuarios, on_delete=models.CASCADE)
    id_carpeta = models.ForeignKey(Carpeta, null=True, blank=True, on_delete=models.SET_NULL)
    descripcion = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    version = models.IntegerField(default=1)

class VinculoDocumento(models.Model):
    id_vinculo = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_documento = models.ForeignKey(Documento, on_delete=models.CASCADE)
    id_entidad_origen = models.UUIDField()
    nombre_modelo_origen = models.CharField(max_length=100)
    tipo_vinculo = models.CharField(max_length=50, null=True, blank=True)
    fecha_vinculo = models.DateTimeField(auto_now_add=True)

class PermisoDocumento(models.Model):
    id_permiso_documento = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_documento = models.ForeignKey(Documento, on_delete=models.CASCADE)
    id_usuario = models.ForeignKey(Usuarios, null=True, blank=True, on_delete=models.CASCADE)
    id_rol = models.ForeignKey('core.Roles', null=True, blank=True, on_delete=models.CASCADE)
    puede_ver = models.BooleanField(default=True)
    puede_editar = models.BooleanField(default=False)
    puede_eliminar = models.BooleanField(default=False)
    fecha_asignacion = models.DateTimeField(auto_now_add=True)
