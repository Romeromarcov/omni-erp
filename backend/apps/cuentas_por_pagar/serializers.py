from rest_framework import serializers
from .models import CuentaPorPagar

class CuentaPorPagarSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuentaPorPagar
        fields = '__all__'
