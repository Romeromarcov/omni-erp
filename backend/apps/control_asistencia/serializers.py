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
        fields = '__all__'

class AsignacionHorarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.AsignacionHorario
        fields = '__all__'

class RegistroAsistenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.RegistroAsistencia
        fields = '__all__'

class ResumenAsistenciaDiarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ResumenAsistenciaDiario
        fields = '__all__'
