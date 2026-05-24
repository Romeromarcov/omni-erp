from rest_framework import serializers

from .models import PersonalizacionConfig


class PersonalizacionConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalizacionConfig
        fields = "__all__"
        read_only_fields = ["id_config", "fecha_creacion"]
