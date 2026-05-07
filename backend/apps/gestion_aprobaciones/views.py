from rest_framework import viewsets
from .models import TipoAprobacion, FlujoAprobacion, SolicitudAprobacion, RegistroAprobacion
from .serializers import TipoAprobacionSerializer, FlujoAprobacionSerializer, SolicitudAprobacionSerializer, RegistroAprobacionSerializer
from apps.core.viewsets import BaseModelViewSet

class TipoAprobacionViewSet(BaseModelViewSet):
    queryset = TipoAprobacion.objects.all()
    serializer_class = TipoAprobacionSerializer

class FlujoAprobacionViewSet(BaseModelViewSet):
    queryset = FlujoAprobacion.objects.all()
    serializer_class = FlujoAprobacionSerializer

class SolicitudAprobacionViewSet(BaseModelViewSet):
    queryset = SolicitudAprobacion.objects.all()
    serializer_class = SolicitudAprobacionSerializer

class RegistroAprobacionViewSet(BaseModelViewSet):
    queryset = RegistroAprobacion.objects.all()
    serializer_class = RegistroAprobacionSerializer
