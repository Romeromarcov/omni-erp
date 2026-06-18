"""Serializers para el módulo de Agentes IA (M9)."""
from rest_framework import serializers

from .models import PrediccionAgente


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
