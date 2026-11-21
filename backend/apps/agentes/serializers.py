"""Serializers para el módulo de Agentes IA (M9 / Plan 05 P2-2)."""

from rest_framework import serializers

from .models import EjecucionAgente, PrediccionAgente


class PrediccionAgenteSerializer(serializers.ModelSerializer):
    esta_vigente = serializers.SerializerMethodField()

    def get_esta_vigente(self, obj):
        return obj.resultado_humano == "pendiente"

    class Meta:
        model = PrediccionAgente
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_prediccion",
            "esta_vigente",
            "agente",
            "input_texto",
            "input_monto",
            "input_metadata",
            "categoria_predicha",
            "confianza",
            "razonamiento",
            "alternativas",
            "resultado_humano",
            "categoria_correcta",
            "modelo_llm",
            "latencia_ms",
            "fecha_prediccion",
            "id_empresa",
        ]
        read_only_fields = [
            "id_prediccion",
            "fecha_prediccion",
            "modelo_llm",
            "latencia_ms",
        ]


class EjecucionAgenteSerializer(serializers.ModelSerializer):
    """Serializer de solo lectura para ejecuciones asíncronas de agentes IA."""

    class Meta:
        model = EjecucionAgente
        fields = [
            "id_ejecucion",
            "agente",
            "estado",
            "celery_task_id",
            "parametros",
            "resultado",
            "mensaje_error",
            "iniciado_por",
            "fecha_creacion",
            "fecha_inicio",
            "fecha_fin",
            "id_empresa",
        ]
        read_only_fields = [
            "id_ejecucion",
            "agente",
            "estado",
            "celery_task_id",
            "parametros",
            "resultado",
            "mensaje_error",
            "iniciado_por",
            "fecha_creacion",
            "fecha_inicio",
            "fecha_fin",
            "id_empresa",
        ]


class AnalizarCobranzaInputSerializer(serializers.Serializer):
    """Parámetros de entrada para encolar ``cobranza_estratega``."""

    empresa_id = serializers.UUIDField(required=False)
    persistir = serializers.BooleanField(required=False, default=False)


class AnalizarReordenInputSerializer(serializers.Serializer):
    """Parámetros de entrada para encolar ``reorden_sugeridor``."""

    empresa_id = serializers.UUIDField(required=False)
    solo_alertas = serializers.BooleanField(required=False, default=True)
    persistir = serializers.BooleanField(required=False, default=False)


class AnalizarPersonalizacionInputSerializer(serializers.Serializer):
    """Parámetros de entrada para encolar ``personalizacion_capa2``."""

    empresa_id = serializers.UUIDField(required=False)


class ClasificarGastoInputSerializer(serializers.Serializer):
    """Parámetros de entrada para encolar ``clasificador_gastos``."""

    gasto_id = serializers.UUIDField(required=True)
    aplicar = serializers.BooleanField(required=False, default=False)
