from rest_framework import serializers
from .models import PlantillaMigracion, ProcesoMigracion, DetalleErrorMigracion

class PlantillaMigracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantillaMigracion
        fields = '__all__'

class ProcesoMigracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcesoMigracion
        fields = '__all__'

class DetalleErrorMigracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleErrorMigracion
        fields = '__all__'
