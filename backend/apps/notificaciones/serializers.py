from rest_framework import serializers

from apps.core.models import Notificacion

from .models import CanalNotificacion, MensajeChatterDocumento


class NotificacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notificacion
        fields = [
            "id_notificacion",
            "tipo",
            "titulo",
            "mensaje",
            "leida",
            "fecha_lectura",
            "url_accion",
            "metadata",
            "fecha_creacion",
        ]
        read_only_fields = fields
        ref_name = "NotificacionApp"  # evita colisión OpenAPI con core.NotificacionSerializer


class MensajeChatterDocumentoSerializer(serializers.ModelSerializer):
    autor_username = serializers.CharField(source="autor.username", read_only=True, default=None)

    class Meta:
        model = MensajeChatterDocumento
        fields = [
            "id_mensaje",
            "id_empresa",
            "tipo_documento",
            "documento_id",
            "autor",
            "autor_username",
            "canal",
            "es_nota_interna",
            "destinatario_telefono",
            "cuerpo",
            "estado_envio",
            "provider_message_id",
            "metadata_json",
            "fecha_creacion",
        ]
        read_only_fields = fields


class CrearChatterInputSerializer(serializers.Serializer):
    id_empresa = serializers.UUIDField(required=False, allow_null=True)
    tipo_documento = serializers.ChoiceField(choices=[c[0] for c in MensajeChatterDocumento.TIPOS_DOCUMENTO])
    documento_id = serializers.UUIDField()
    cuerpo = serializers.CharField(max_length=4000)
    es_nota_interna = serializers.BooleanField(required=False, default=True)
    canal = serializers.ChoiceField(
        choices=CanalNotificacion.choices, required=False, default=CanalNotificacion.IN_APP
    )
    destinatario_telefono = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")


class EnviarWhatsAppInputSerializer(serializers.Serializer):
    id_empresa = serializers.UUIDField(required=False, allow_null=True)
    tipo_documento = serializers.ChoiceField(choices=[c[0] for c in MensajeChatterDocumento.TIPOS_DOCUMENTO])
    documento_id = serializers.UUIDField()
    telefono = serializers.CharField(max_length=30)
    plantilla = serializers.ChoiceField(
        choices=["libre", "cotizacion", "cobranza", "tracking"], required=False, default="libre"
    )
    cuerpo = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    contexto = serializers.DictField(required=False, default=dict)
