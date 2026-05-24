from rest_framework import serializers

from .models import CatalogoValor, ParametroSistema, TipoDocumento


class TipoDocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoDocumento
        fields = "__all__"


class ParametroSistemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParametroSistema
        fields = "__all__"


class CatalogoValorSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogoValor
        fields = "__all__"
