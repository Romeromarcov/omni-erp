import uuid
from apps.core.uuid import uuid7

from django.contrib.auth.models import AbstractUser
from django.db import models


class HorarioTrabajo(models.Model):
    id_horario = models.UUIDField(primary_key=True, default=uuid7)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    nombre_horario = models.CharField(max_length=100)
    descripcion = models.TextField(null=True, blank=True)
    dias_semana_json = models.JSONField(null=True, blank=True)
    total_horas_semanales = models.DecimalField(max_digits=5, decimal_places=2)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return str(self.id_empresa)


class AsignacionHorario(models.Model):
    id_asignacion_horario = models.UUIDField(primary_key=True, default=uuid7)
    id_empleado = models.ForeignKey(
        "rrhh.Empleado",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="asignaciones_horario",
    )
    id_horario = models.ForeignKey("HorarioTrabajo", on_delete=models.CASCADE)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return str(self.id_empleado_id)


class RegistroAsistencia(models.Model):
    id_registro_asistencia = models.UUIDField(primary_key=True, default=uuid7)
    id_empleado = models.ForeignKey(
        "rrhh.Empleado",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="registros_asistencia",
    )
    fecha_hora_marcado = models.DateTimeField()
    tipo_marcado = models.CharField(
        max_length=20,
        choices=[
            ("ENTRADA", "Entrada"),
            ("SALIDA", "Salida"),
            ("INICIO_DESCANSO", "Inicio Descanso"),
            ("FIN_DESCANSO", "Fin Descanso"),
        ],
    )
    metodo_marcado = models.CharField(
        max_length=50,
        choices=[
            ("BIOMETRICO", "Biométrico"),
            ("MANUAL", "Manual"),
            ("WEB", "Web"),
            ("MOVIL", "Móvil"),
            ("GPS", "GPS"),
        ],
    )
    ubicacion_gps_json = models.JSONField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.id_empleado_id)


class ResumenAsistenciaDiario(models.Model):
    id_resumen_diario = models.UUIDField(primary_key=True, default=uuid7)
    id_empleado = models.ForeignKey(
        "rrhh.Empleado",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resumenes_asistencia",
    )
    fecha = models.DateField()
    hora_entrada_real = models.TimeField(null=True, blank=True)
    hora_salida_real = models.TimeField(null=True, blank=True)
    horas_trabajadas_netas = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    horas_extras_normal = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    horas_extras_feriado = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    minutos_tardanza = models.IntegerField(default=0)
    es_ausencia = models.BooleanField(default=False)
    id_licencia_asociada = models.ForeignKey(
        "rrhh.LicenciaEmpleado",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resumenes_asistencia",
    )
    estado_revision = models.CharField(
        max_length=20, choices=[("PENDIENTE", "Pendiente"), ("REVISADO", "Revisado"), ("APROBADO", "Aprobado")]
    )
    observaciones_supervisor = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["id_empleado", "fecha"]]

    def __str__(self):
        return str(self.id_empleado_id)
