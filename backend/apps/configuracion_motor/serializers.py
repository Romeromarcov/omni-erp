from rest_framework import serializers

from .models import CatalogoValor, ParametroSistema, TipoDocumento


class TipoDocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoDocumento
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_tipo_documento",
            "codigo",
            "nombre",
            "descripcion",
            "modulo_origen",
            "es_transaccional",
            "prefijo_correlativo",
            "ultimo_correlativo",
        ]


class ParametroSistemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParametroSistema
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_parametro",
            "nombre_parametro",
            "codigo_parametro",
            "valor_parametro",
            "tipo_dato",
            "descripcion",
            "activo",
            "id_empresa",
        ]


class CatalogoValorSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogoValor
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_catalogo_valor",
            "codigo_catalogo",
            "valor",
            "descripcion",
            "orden",
            "activo",
        ]
