"""Serializers para el módulo SaaS (M10-T5)."""
from rest_framework import serializers

from .models import Plan, Suscripcion


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = "__all__"
        read_only_fields = ["id_plan", "fecha_creacion", "fecha_actualizacion"]


class SuscripcionSerializer(serializers.ModelSerializer):
    esta_vigente = serializers.BooleanField(read_only=True)
    dias_restantes = serializers.IntegerField(read_only=True)
    plan_nombre = serializers.CharField(source="id_plan.nombre", read_only=True)
    plan_nivel = serializers.CharField(source="id_plan.nivel", read_only=True)

    class Meta:
        model = Suscripcion
        fields = "__all__"
        read_only_fields = [
            "id_suscripcion",
            "fecha_cancelacion",
            "fecha_suspension",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
