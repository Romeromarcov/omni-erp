import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

class CategoriaGasto(models.Model):
    id_categoria_gasto = models.UUIDField(primary_key=True, default=uuid.uuid4)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    nombre_categoria = models.CharField(max_length=100)
    descripcion = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return str(self.id_empresa)

class Gasto(models.Model):
    id_gasto = models.UUIDField(primary_key=True, default=uuid.uuid4)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    fecha_gasto = models.DateField()
    descripcion = models.TextField()
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    id_moneda = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE)
    id_categoria_gasto = models.ForeignKey("CategoriaGasto", on_delete=models.CASCADE)
    # id_empleado_responsable = models.ForeignKey("rrhh.Empleado", on_delete=models.CASCADE, null=True, blank=True)  # Temporalmente comentado
    id_empleado_responsable_temp = models.UUIDField(null=True, blank=True)  # Campo temporal
    estado_gasto = models.CharField(max_length=20, choices=[("PENDIENTE_APROBACION", "Pendiente Aprobación"), ("APROBADO", "Aprobado"), ("RECHAZADO", "Rechazado"), ("REEMBOLSADO", "Reembolsado"), ("CONTABILIZADO", "Contabilizado")])
    # id_usuario_registro = models.ForeignKey("core.Usuarios", on_delete=models.CASCADE)  # Temporalmente comentado
    id_usuario_registro_temp = models.UUIDField(null=True, blank=True)  # Campo temporal
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.id_empresa)

class ReembolsoGasto(models.Model):
    id_reembolso = models.UUIDField(primary_key=True, default=uuid.uuid4)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    id_gasto = models.ForeignKey("Gasto", on_delete=models.CASCADE)
    # id_empleado = models.ForeignKey("rrhh.Empleado", on_delete=models.CASCADE)  # Temporalmente comentado
    id_empleado_temp = models.UUIDField(null=True, blank=True)  # Campo temporal
    monto_reembolso = models.DecimalField(max_digits=18, decimal_places=2)
    id_moneda = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE)
    id_metodo_pago = models.ForeignKey("finanzas.MetodoPago", on_delete=models.CASCADE)
    fecha_reembolso = models.DateField()
    estado_reembolso = models.CharField(max_length=20, choices=[("PENDIENTE", "Pendiente"), ("PAGADO", "Pagado"), ("ANULADO", "Anulado")])
    # id_usuario_registro = models.ForeignKey("core.Usuarios", on_delete=models.CASCADE)  # Temporalmente comentado
    id_usuario_registro_temp = models.UUIDField(null=True, blank=True)  # Campo temporal
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.id_empresa)
