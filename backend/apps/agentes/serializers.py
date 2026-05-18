"""Serializers para el módulo de Agentes IA (M9)."""
from rest_framework import serializers

from .models import PrediccionAgente


class PrediccionAgenteSerializer(serializers.ModelSerializer):
    esta_vigente = serializers.SerializerMethodField()

    def get_esta_vigente(self, obj):
        return obj.resultado_humano == "pendiente"

    class Meta:
        model = PrediccionAgente
        fields = "__all__"
        read_only_fields = [
            "id_prediccion",
            "fecha_prediccion",
            "modelo_llm",
            "latencia_ms",
        ]
