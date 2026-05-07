from rest_framework import serializers
from .models import LogAuditoria

class LogAuditoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogAuditoria
        fields = '__all__'
