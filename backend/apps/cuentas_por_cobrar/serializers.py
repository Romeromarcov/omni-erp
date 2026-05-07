from rest_framework import serializers
from .models import CuentaPorCobrar

class CuentaPorCobrarSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuentaPorCobrar
        fields = '__all__'
