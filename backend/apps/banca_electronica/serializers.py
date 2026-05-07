from rest_framework import serializers
from .models import CuentaBancariaEmpresa

class CuentaBancariaEmpresaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuentaBancariaEmpresa
        fields = '__all__'
