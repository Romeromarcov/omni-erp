from rest_framework import serializers

from .models import CuentaBancariaEmpresa


class CuentaBancariaEmpresaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuentaBancariaEmpresa
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "referencia_externa",
            "documento_json",
            "banco",
            "numero_cuenta",
            "tipo_cuenta",
            "saldo_actual",
            "activa",
            "empresa",
            "moneda",
        ]
        ref_name = "CuentaBancariaEmpresaBanca"  # evita colisión OpenAPI con finanzas
