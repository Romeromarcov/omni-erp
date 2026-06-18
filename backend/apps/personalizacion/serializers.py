from rest_framework import serializers

from .models import PersonalizacionConfig


class PersonalizacionConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalizacionConfig
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_config",
            "version",
            "descripcion",
            "config_yaml",
            "config_dict",
            "activo",
            "fecha_creacion",
            "fecha_aplicacion",
            "resultado_aplicacion",
            "id_empresa",
        ]
        read_only_fields = ["id_config", "fecha_creacion"]
