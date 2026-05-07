from django.db import models
from apps.core.models import Empresa
import uuid

class Cargo(models.Model):
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, null=True, blank=True)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class Empleado(models.Model):
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='empleados')
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    cedula = models.CharField(max_length=20, unique=True)
    cargo = models.ForeignKey(Cargo, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_ingreso = models.DateField()
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.cedula})"


class Beneficio(models.Model):
    id_beneficio = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='beneficios')
    nombre_beneficio = models.CharField(max_length=100)
    descripcion = models.TextField(null=True, blank=True)
    tipo_beneficio = models.CharField(max_length=20, choices=[
        ('MONETARIO', 'Monetario'),
        ('NO_MONETARIO', 'No Monetario'),
        ('TIEMPO', 'Tiempo'),
        ('SALUD', 'Salud'),
        ('EDUCACION', 'Educación'),
        ('TRANSPORTE', 'Transporte'),
        ('ALIMENTACION', 'Alimentación'),
        ('OTRO', 'Otro')
    ])
    monto_fijo = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    porcentaje_salario = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    es_obligatorio = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rrhh_beneficio'
        verbose_name = 'Beneficio'
        verbose_name_plural = 'Beneficios'

    def __str__(self):
        return self.nombre_beneficio


class BeneficioEmpleado(models.Model):
    id_beneficio_empleado = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empleado = models.ForeignKey('Empleado', on_delete=models.CASCADE, related_name='beneficios')
    id_beneficio = models.ForeignKey('Beneficio', on_delete=models.CASCADE, related_name='asignaciones')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    monto_personalizado = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    porcentaje_personalizado = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    estado = models.CharField(max_length=20, choices=[
        ('ACTIVO', 'Activo'),
        ('SUSPENDIDO', 'Suspendido'),
        ('TERMINADO', 'Terminado')
    ], default='ACTIVO')
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rrhh_beneficio_empleado'
        verbose_name = 'Beneficio de Empleado'
        verbose_name_plural = 'Beneficios de Empleados'

    def __str__(self):
        return f"{self.id_empleado.nombre} {self.id_empleado.apellido} - {self.id_beneficio.nombre_beneficio}"


class TipoLicencia(models.Model):
    id_tipo_licencia = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='tipos_licencia')
    nombre_tipo = models.CharField(max_length=100)
    descripcion = models.TextField(null=True, blank=True)
    es_remunerada = models.BooleanField(default=True)
    dias_maximos_por_año = models.IntegerField(null=True, blank=True)
    requiere_aprobacion = models.BooleanField(default=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rrhh_tipo_licencia'
        verbose_name = 'Tipo de Licencia'
        verbose_name_plural = 'Tipos de Licencia'

    def __str__(self):
        return self.nombre_tipo


class LicenciaEmpleado(models.Model):
    id_licencia = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empleado = models.ForeignKey('Empleado', on_delete=models.CASCADE, related_name='licencias')
    id_tipo_licencia = models.ForeignKey('TipoLicencia', on_delete=models.CASCADE, related_name='licencias')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    dias_solicitados = models.IntegerField()
    motivo = models.TextField()
    estado = models.CharField(max_length=20, choices=[
        ('PENDIENTE', 'Pendiente'),
        ('APROBADA', 'Aprobada'),
        ('RECHAZADA', 'Rechazada'),
        ('EN_CURSO', 'En Curso'),
        ('FINALIZADA', 'Finalizada'),
        ('CANCELADA', 'Cancelada')
    ], default='PENDIENTE')
    id_aprobador = models.ForeignKey('Empleado', on_delete=models.SET_NULL, null=True, blank=True, related_name='licencias_aprobadas')
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    observaciones_aprobacion = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rrhh_licencia_empleado'
        verbose_name = 'Licencia de Empleado'
        verbose_name_plural = 'Licencias de Empleados'

    def __str__(self):
        return f"{self.id_empleado.nombre} {self.id_empleado.apellido} - {self.id_tipo_licencia.nombre_tipo}"
