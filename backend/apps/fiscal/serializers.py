from rest_framework import serializers

from .models import ConfiguracionFiscalEmpresa, TasaIVAEmpresa


class ConfiguracionFiscalEmpresaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionFiscalEmpresa
        fields = "__all__"
        read_only_fields = ["fecha_creacion", "fecha_actualizacion"]


class TasaIVAEmpresaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TasaIVAEmpresa
        fields = "__all__"
        read_only_fields = ["fecha_creacion"]
