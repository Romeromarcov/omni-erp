from rest_framework import serializers
from . import models

# Serializadores para nomina
# Ejemplo:
# class TuModeloSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.TuModelo
#         fields = '__all__'

# Serializadores agregados automáticamente

class PeriodoNominaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PeriodoNomina
        fields = '__all__'

class ConceptoNominaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ConceptoNomina
        fields = '__all__'

class ProcesoNominaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProcesoNomina
        fields = '__all__'

class NominaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Nomina
        fields = '__all__'

class DetalleNominaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DetalleNomina
        fields = '__all__'

class ProcesoNominaExtrasalarialSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProcesoNominaExtrasalarial
        fields = '__all__'

class NominaExtrasalarialSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.NominaExtrasalarial
        fields = '__all__'
