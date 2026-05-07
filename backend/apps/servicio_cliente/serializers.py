from rest_framework import serializers
from . import models

# Serializadores para servicio_cliente
# Ejemplo:
# class TuModeloSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.TuModelo
#         fields = '__all__'

# Serializadores agregados automáticamente

class CategoriaTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CategoriaTicket
        fields = '__all__'

class TicketSoporteSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.TicketSoporte
        fields = '__all__'

class InteraccionTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.InteraccionTicket
        fields = '__all__'

class BaseConocimientoArticuloSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.BaseConocimientoArticulo
        fields = '__all__'

class FeedbackClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedbackCliente
        fields = '__all__'
