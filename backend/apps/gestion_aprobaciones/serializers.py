from rest_framework import serializers
from .models import TipoAprobacion, FlujoAprobacion, SolicitudAprobacion, RegistroAprobacion
from apps.core.serializers import BaseModelSerializer

class TipoAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = TipoAprobacion
        fields = '__all__'

class FlujoAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = FlujoAprobacion
        fields = '__all__'

class SolicitudAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = SolicitudAprobacion
        fields = '__all__'

class RegistroAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = RegistroAprobacion
        fields = '__all__'
