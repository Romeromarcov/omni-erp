from rest_framework import serializers

from .models import ConfiguracionFiscalEmpresa, TasaIVAEmpresa


class ConfiguracionFiscalEmpresaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionFiscalEmpresa
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "contribuyente_iva",
            "aplica_igtf",
            "tasa_igtf",
            "fecha_creacion",
            "fecha_actualizacion",
            "id_empresa",
        ]
        read_only_fields = ["fecha_creacion", "fecha_actualizacion"]


class TasaIVAEmpresaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TasaIVAEmpresa
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "tipo",
            "nombre",
            "tasa",
            "activo",
            "fecha_creacion",
            "id_empresa",
        ]
        read_only_fields = ["fecha_creacion"]
