from django.db import models
from apps.core.models import Empresa
import uuid

class TipoDocumento(models.Model):
    id_tipo_documento = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(null=True, blank=True)
    modulo_origen = models.CharField(max_length=50)
    es_transaccional = models.BooleanField(default=True)
    prefijo_correlativo = models.CharField(max_length=10, null=True, blank=True)
    ultimo_correlativo = models.IntegerField(default=0)

class ParametroSistema(models.Model):
    id_parametro = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(Empresa, null=True, blank=True, on_delete=models.CASCADE)
    nombre_parametro = models.CharField(max_length=100)
    codigo_parametro = models.CharField(max_length=50, unique=True)
    valor_parametro = models.TextField()
    tipo_dato = models.CharField(max_length=20, choices=[('TEXTO','TEXTO'),('NUMERO','NUMERO'),('BOOLEANO','BOOLEANO'),('FECHA','FECHA')])
    descripcion = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)

class CatalogoValor(models.Model):
    id_catalogo_valor = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codigo_catalogo = models.CharField(max_length=50)
    valor = models.CharField(max_length=100)
    descripcion = models.TextField(null=True, blank=True)
    orden = models.IntegerField(default=0)
    activo = models.BooleanField(default=True)
