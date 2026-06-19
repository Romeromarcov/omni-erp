from rest_framework import serializers

from .models import ConfiguracionIntegracion, LogIntegracion, MapeoCampo


class ConfiguracionIntegracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionIntegracion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_configuracion",
            "nombre_integracion",
            "tipo_integracion",
            "url_endpoint",
            "credenciales_json",
            "formato_datos",
            "activo",
            "fecha_creacion",
            "id_empresa",
        ]


class LogIntegracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogIntegracion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_log_integracion",
            "fecha_hora",
            "tipo_transaccion",
            "id_entidad_origen",
            "nombre_modelo_origen",
            "request_payload_json",
            "response_payload_json",
            "estado_integracion",
            "mensaje_error",
            "duracion_ms",
            "id_configuracion",
        ]


class MapeoCampoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MapeoCampo
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_mapeo_campo",
            "nombre_campo_interno",
            "nombre_campo_externo",
            "activo",
            "id_configuracion_integracion",
        ]
