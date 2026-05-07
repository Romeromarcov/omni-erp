
from rest_framework import viewsets
from .models import Caja, MovimientoInternoFondo, OperacionCambioDivisa
from .serializers import CajaSerializer, MovimientoInternoFondoSerializer, OperacionCambioDivisaSerializer
from apps.core.viewsets import BaseModelViewSet


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
