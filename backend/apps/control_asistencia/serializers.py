from rest_framework import serializers

from . import models

# Serializadores para control_asistencia
# Ejemplo:
# class TuModeloSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.TuModelo
#         fields = '__all__'

# Serializadores agregados automáticamente


class HorarioTrabajoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.HorarioTrabajo
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_horario",
            "nombre_horario",
            "descripcion",
            "dias_semana_json",
            "total_horas_semanales",
            "activo",
            "id_empresa",
        ]


class AsignacionHorarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.AsignacionHorario
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_asignacion_horario",
            "fecha_inicio",
            "fecha_fin",
            "activo",
            "id_empleado",
            "id_horario",
        ]


class RegistroAsistenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.RegistroAsistencia
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_registro_asistencia",
            "fecha_hora_marcado",
            "tipo_marcado",
            "metodo_marcado",
            "ubicacion_gps_json",
            "observaciones",
            "fecha_creacion",
            "id_empleado",
        ]


class ResumenAsistenciaDiarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ResumenAsistenciaDiario
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_resumen_diario",
            "fecha",
            "hora_entrada_real",
            "hora_salida_real",
            "horas_trabajadas_netas",
            "horas_extras_normal",
            "horas_extras_feriado",
            "minutos_tardanza",
            "es_ausencia",
            "estado_revision",
            "observaciones_supervisor",
            "fecha_creacion",
            "id_empleado",
            "id_licencia_asociada",
        ]
