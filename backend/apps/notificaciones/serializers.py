from rest_framework import serializers

from apps.core.models import Notificacion


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
