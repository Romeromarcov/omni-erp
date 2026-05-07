from rest_framework import serializers
from . import models

# Serializadores para despacho
# Ejemplo:
# class TuModeloSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.TuModelo
#         fields = '__all__'

# Serializadores agregados automáticamente

class DespachoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Despacho
        fields = '__all__'

class DetalleDespachoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DetalleDespacho
        fields = '__all__'
