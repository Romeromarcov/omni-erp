from rest_framework import serializers

from apps.core.serializers import BaseModelSerializer

from .models import FlujoAprobacion, RegistroAprobacion, SolicitudAprobacion, TipoAprobacion


class TipoAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = TipoAprobacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_tipo_aprobacion",
            "codigo_tipo",
            "nombre_tipo",
            "descripcion",
            "modulo_origen",
            "activo",
            "id_empresa",
        ]


class FlujoAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = FlujoAprobacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_flujo_aprobacion",
            "orden_etapa",
            "nombre_etapa",
            "monto_minimo",
            "monto_maximo",
            "activo",
            "id_tipo_aprobacion",
            "rol_aprobador",
            "id_usuario_aprobador",
        ]


class SolicitudAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = SolicitudAprobacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_solicitud_aprobacion",
            "id_entidad_origen",
            "nombre_modelo_origen",
            "fecha_solicitud",
            "estado_solicitud",
            "comentarios_solicitante",
            "fecha_ultima_actualizacion",
            "id_tipo_aprobacion",
            "id_usuario_solicitante",
            "etapa_actual_flujo",
        ]


class RegistroAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = RegistroAprobacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_registro_aprobacion",
            "fecha_decision",
            "tipo_decision",
            "comentarios",
            "id_solicitud_aprobacion",
            "id_flujo_aprobacion_etapa",
            "id_usuario_aprobador",
        ]
