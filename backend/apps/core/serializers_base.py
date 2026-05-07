# Serializers base para herencia
from rest_framework import serializers

class BaseModelSerializer(serializers.ModelSerializer):
    class Meta:
        abstract = True
