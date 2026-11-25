"""Serializers para el módulo de Agentes IA (M9 / Plan 05 P2-2)."""

from rest_framework import serializers

from .models import ConsumoLLM, EjecucionAgente, PrediccionAgente


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


class CalificarLeadConnectInputSerializer(serializers.Serializer):
    """Parámetros de entrada para encolar ``connect_calificador``."""

    lead_id = serializers.UUIDField(required=True)


class ProponerSeguimientoConnectInputSerializer(serializers.Serializer):
    """Parámetros de entrada para encolar ``connect_seguimiento``."""

    lead_id = serializers.UUIDField(required=True)


class ConsumoLLMSerializer(serializers.ModelSerializer):
    """Serializer de solo lectura para registros de consumo y costo LLM (Plan 05 P2-3)."""

    class Meta:
        model = ConsumoLLM
        fields = [
            "id_consumo",
            "id_empresa",
            "proveedor",
            "uso",
            "modelo",
            "tokens_entrada",
            "tokens_salida",
            "costo_estimado_usd",
            "latencia_ms",
            "creado_en",
        ]
        read_only_fields = fields


class ConsumoLLMPorModeloSerializer(serializers.Serializer):
    """Desglose agregado de consumo LLM por modelo."""

    modelo = serializers.CharField(read_only=True)
    llamadas = serializers.IntegerField(read_only=True)
    tokens_entrada_total = serializers.IntegerField(read_only=True)
    tokens_salida_total = serializers.IntegerField(read_only=True)
    costo_total_usd = serializers.DecimalField(
        max_digits=16,
        decimal_places=6,
        coerce_to_string=True,
        read_only=True,
    )


class ConsumoLLMPorUsoSerializer(serializers.Serializer):
    """Desglose agregado de consumo LLM por uso."""

    uso = serializers.CharField(read_only=True)
    llamadas = serializers.IntegerField(read_only=True)
    tokens_entrada_total = serializers.IntegerField(read_only=True)
    tokens_salida_total = serializers.IntegerField(read_only=True)
    costo_total_usd = serializers.DecimalField(
        max_digits=16,
        decimal_places=6,
        coerce_to_string=True,
        read_only=True,
    )


class ConsumoLLMResumenSerializer(serializers.Serializer):
    """Resumen agregado de consumo LLM (totales y desglose por modelo/uso)."""

    llamadas = serializers.IntegerField(read_only=True)
    tokens_entrada_total = serializers.IntegerField(read_only=True)
    tokens_salida_total = serializers.IntegerField(read_only=True)
    costo_total_usd = serializers.DecimalField(
        max_digits=16,
        decimal_places=6,
        coerce_to_string=True,
        read_only=True,
    )
    latencia_promedio_ms = serializers.IntegerField(read_only=True)
    por_modelo = ConsumoLLMPorModeloSerializer(many=True, read_only=True)
    por_uso = ConsumoLLMPorUsoSerializer(many=True, read_only=True)


class EjecutarAgenteOperativoInputSerializer(serializers.Serializer):
    """Entrada para ejecutar cualquiera de los 5 agentes IA operativos (Plan 09 Fase 8.2)."""

    id_empresa = serializers.UUIDField(required=False, allow_null=True)
    agente = serializers.ChoiceField(choices=["COBRANZA", "TESORERO", "LOGISTICO", "COMPRADOR", "CFO_COPILOT"])
    persistir = serializers.BooleanField(required=False, default=True)
    limite = serializers.IntegerField(required=False, default=25, min_value=1, max_value=100)
