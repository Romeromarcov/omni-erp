from rest_framework import serializers
from .models import PlanCuentas, AsientoContable, DetalleAsiento

class PlanCuentasSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanCuentas
        fields = '__all__'

class DetalleAsientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleAsiento
        fields = '__all__'

class AsientoContableSerializer(serializers.ModelSerializer):
    detalles = DetalleAsientoSerializer(many=True, read_only=True, source='detalleasiento_set')
    
    class Meta:
        model = AsientoContable
        fields = '__all__'
        
    def validate(self, data):
        """Validación personalizada para asientos contables"""
        # Aquí podrías agregar validaciones como que el asiento cuadre (debe = haber)
        return data
