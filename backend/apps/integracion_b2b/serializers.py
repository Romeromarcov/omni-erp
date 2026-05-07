from rest_framework import serializers
from .models import ConfiguracionIntegracion, LogIntegracion, MapeoCampo

class ConfiguracionIntegracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionIntegracion
        fields = '__all__'

class LogIntegracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogIntegracion
        fields = '__all__'

class MapeoCampoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MapeoCampo
        fields = '__all__'
