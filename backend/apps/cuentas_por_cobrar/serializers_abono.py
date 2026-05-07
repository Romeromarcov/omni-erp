from rest_framework import serializers
from .models import AbonoCxC

class AbonoCxCSerializer(serializers.ModelSerializer):
    class Meta:
        model = AbonoCxC
        fields = '__all__'
