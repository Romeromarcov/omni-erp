import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

class PlanCuentas(models.Model):
    id_cuenta_contable = models.UUIDField(primary_key=True, default=uuid.uuid4)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    codigo_cuenta = models.CharField(max_length=50, unique=True)
    nombre_cuenta = models.CharField(max_length=255)
    tipo_cuenta = models.CharField(max_length=50, choices=[("ACTIVO", "Activo"), ("PASIVO", "Pasivo"), ("PATRIMONIO", "Patrimonio"), ("INGRESO", "Ingreso"), ("GASTO", "Gasto"), ("COSTO", "Costo")])
    naturaleza = models.CharField(max_length=10, choices=[("DEUDORA", "Deudora"), ("ACREEDORA", "Acreedora")])
    id_cuenta_padre = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True)
    nivel = models.IntegerField()
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.nombre_cuenta)

class AsientoContable(models.Model):
    id_asiento = models.UUIDField(primary_key=True, default=uuid.uuid4)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    fecha_asiento = models.DateField()
    numero_asiento = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField()
    id_documento_origen = models.UUIDField(null=True, blank=True)
    nombre_modelo_origen = models.CharField(max_length=100, null=True, blank=True)
    estado_asiento = models.CharField(max_length=20, choices=[("BORRADOR", "Borrador"), ("APROBADO", "Aprobado"), ("ANULADO", "Anulado")])
    # id_usuario_registro = models.ForeignKey("core.Usuarios", on_delete=models.CASCADE)  # Temporalmente comentado
    id_usuario_registro_temp = models.UUIDField(null=True, blank=True)  # Campo temporal
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.numero_asiento)

class DetalleAsiento(models.Model):
    id_detalle_asiento = models.UUIDField(primary_key=True, default=uuid.uuid4)
    id_asiento = models.ForeignKey("AsientoContable", on_delete=models.CASCADE)
    id_cuenta_contable = models.ForeignKey("PlanCuentas", on_delete=models.CASCADE)
    debe = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    haber = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    descripcion_detalle = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.id_asiento)
