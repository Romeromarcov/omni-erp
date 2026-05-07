from rest_framework import serializers
from . import models

# Serializadores para gastos
# Ejemplo:
# class TuModeloSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.TuModelo
#         fields = '__all__'

# Serializadores agregados automáticamente

class CategoriaGastoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CategoriaGasto
        fields = '__all__'

class GastoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Gasto
        fields = '__all__'

class ReembolsoGastoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ReembolsoGasto
        fields = '__all__'
