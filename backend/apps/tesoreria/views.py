from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet

from .models import Caja, MovimientoInternoFondo, OperacionCambioDivisa
from .serializers import CajaSerializer, MovimientoInternoFondoSerializer, OperacionCambioDivisaSerializer


class CajaViewSet(BaseModelViewSet):
    queryset = Caja.objects.all()
    serializer_class = CajaSerializer


class MovimientoInternoFondoViewSet(BaseModelViewSet):
    queryset = MovimientoInternoFondo.objects.all()
    serializer_class = MovimientoInternoFondoSerializer

    def perform_create(self, serializer):
        serializer.save()


class OperacionCambioDivisaViewSet(BaseModelViewSet):
    queryset = OperacionCambioDivisa.objects.all()
    serializer_class = OperacionCambioDivisaSerializer

    def perform_create(self, serializer):
        serializer.save()
