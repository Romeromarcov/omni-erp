from rest_framework import serializers

from .models import CuentaBancariaEmpresa


class CuentaBancariaEmpresaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuentaBancariaEmpresa
        fields = "__all__"
        ref_name = "CuentaBancariaEmpresaBanca"  # evita colisión OpenAPI con finanzas
