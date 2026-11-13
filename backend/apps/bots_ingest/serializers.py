from rest_framework import serializers

from .models import BotUsuario, IngestaBot


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
    class Meta:
        model = BotUsuario
        fields = [
            "id_bot_usuario",
            "id_empresa",
            "telegram_user_id",
            "usuario",
            "nombre",
            "activo",
        ]
        read_only_fields = ["id_empresa"]
