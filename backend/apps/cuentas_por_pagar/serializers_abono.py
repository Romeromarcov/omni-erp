from rest_framework import serializers

from .models import AbonoCxP


class AbonoCxPSerializer(serializers.ModelSerializer):
    class Meta:
        model = AbonoCxP
        fields = "__all__"
