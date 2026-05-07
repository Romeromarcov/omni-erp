from rest_framework import serializers
from . import models

# Serializadores para costos
# Ejemplo:
# class TuModeloSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.TuModelo
#         fields = '__all__'

# Serializadores agregados automáticamente

class CostoProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CostoProduccion
        fields = '__all__'

class CostoEstandarProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CostoEstandarProducto
        fields = '__all__'

class AnalisisVariacionCostoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.AnalisisVariacionCosto
        fields = '__all__'
