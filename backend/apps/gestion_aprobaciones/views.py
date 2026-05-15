from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet

from .models import FlujoAprobacion, RegistroAprobacion, SolicitudAprobacion, TipoAprobacion
from .serializers import (
    FlujoAprobacionSerializer,
    RegistroAprobacionSerializer,
    SolicitudAprobacionSerializer,
    TipoAprobacionSerializer,
)


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
