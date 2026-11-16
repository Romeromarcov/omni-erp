from rest_framework import serializers

from .models import BotUsuario, IngestaBot
from .services.control import (
    DatoControlInvalido,
    redactar,
    validar_codigo_bot,
    validar_lista_bots,
)


class IngestaEntradaSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=IngestaBot.Kind.choices)
    draft = serializers.DictField()
    source = serializers.DictField()
    idempotency_key = serializers.CharField(max_length=120)

    def validate_source(self, v):
        if "telegram_user_id" not in v:
            raise serializers.ValidationError("Falta telegram_user_id.")
        return v


class IngestaSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestaBot
        fields = [
            "id_ingesta",
            "kind",
            "estado",
            "incompleto",
            "resultado",
            "auto",
            "payload",
            "odoo_ref",
            "error",
            "idempotency_key",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields


class BotUsuarioSerializer(serializers.ModelSerializer):
    telegram_user_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    bots = serializers.ListField(
        child=serializers.CharField(max_length=30),
        required=False,
        allow_empty=True,
        default=list,
    )

    class Meta:
        model = BotUsuario
        fields = [
            "id_bot_usuario",
            "id_empresa",
            "telegram_user_id",
            "usuario",
            "nombre",
            "bots",
            "activo",
        ]
        read_only_fields = ["id_empresa", "activo"]
        validators = []

    def validate_telegram_user_id(self, value: int) -> int:
        qs = BotUsuario.objects.filter(telegram_user_id=value, activo=True)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Este usuario de Telegram ya está vinculado a una cuenta activa."
            )
        return value

    def validate_nombre(self, value: str) -> str:
        return redactar((value or "").strip())

    def validate_bots(self, value):
        try:
            return validar_lista_bots(value)
        except DatoControlInvalido as exc:
            raise serializers.ValidationError(str(exc)) from exc


class BotLatidoEntradaSerializer(serializers.Serializer):
    bot = serializers.CharField(max_length=30)
    nombre = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    version = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    estado = serializers.DictField(required=False, default=dict)

    def validate_bot(self, value: str) -> str:
        try:
            return validar_codigo_bot(value)
        except DatoControlInvalido as exc:
            raise serializers.ValidationError(str(exc)) from exc


class BotControlPatchSerializer(serializers.Serializer):
    habilitado = serializers.BooleanField(required=False)
    nombre = serializers.CharField(max_length=100, required=False)
    parametros = serializers.DictField(required=False)
    chats = serializers.DictField(required=False)
    url_panel = serializers.CharField(max_length=300, required=False, allow_blank=True)
    mensaje = serializers.CharField(max_length=280, required=False, allow_blank=True)
