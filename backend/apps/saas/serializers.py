"""Serializers para el módulo SaaS (M10-T5)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Plan, Suscripcion

User = get_user_model()


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_plan",
            "nombre",
            "nivel",
            "descripcion",
            "precio_mensual",
            "precio_anual",
            "max_usuarios",
            "max_empresas",
            "max_documentos_mes",
            "permite_ia",
            "permite_api",
            "permite_reportes_avanzados",
            "permite_multimoneda",
            "soporte",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_plan", "fecha_creacion", "fecha_actualizacion"]


class SuscripcionSerializer(serializers.ModelSerializer):
    esta_vigente = serializers.BooleanField(read_only=True)
    dias_restantes = serializers.IntegerField(read_only=True)
    plan_nombre = serializers.CharField(source="id_plan.nombre", read_only=True)
    plan_nivel = serializers.CharField(source="id_plan.nivel", read_only=True)

    class Meta:
        model = Suscripcion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_suscripcion",
            "esta_vigente",
            "dias_restantes",
            "plan_nombre",
            "plan_nivel",
            "estado",
            "periodo",
            "fecha_inicio",
            "fecha_fin",
            "fecha_cancelacion",
            "fecha_suspension",
            "renovacion_automatica",
            "monto_pagado",
            "referencia_pago",
            "notas",
            "fecha_creacion",
            "fecha_actualizacion",
            "id_empresa",
            "id_plan",
        ]
        read_only_fields = [
            "id_suscripcion",
            "fecha_cancelacion",
            "fecha_suspension",
            "fecha_creacion",
            "fecha_actualizacion",
        ]


class SignupSerializer(serializers.Serializer):
    """
    Auto-registro de un prospecto (Plan C — Fase C3).

    Valida los datos de la nueva empresa + su usuario administrador. Es un
    endpoint PÚBLICO: nunca acepta `es_superusuario_omni` ni `is_staff` (se
    fuerzan a False en la vista). La creación atómica vive en la vista.
    """

    # Empresa
    empresa_nombre_legal = serializers.CharField(max_length=255)
    empresa_nombre_comercial = serializers.CharField(max_length=255, required=False, allow_blank=True)
    empresa_identificador_fiscal = serializers.CharField(max_length=20, required=False, allow_blank=True)
    empresa_email = serializers.EmailField(required=False, allow_blank=True)

    # Usuario administrador
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    # Plan del trial (opcional). Si no se indica, la vista elige el más económico.
    plan_nivel = serializers.ChoiceField(
        choices=["FREE", "STARTER", "PRO", "ENTERPRISE"],
        required=False,
    )

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("El nombre de usuario ya está en uso.")
        return value

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value
