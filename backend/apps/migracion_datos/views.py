from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet

from .models import DetalleErrorMigracion, PlantillaMigracion, ProcesoMigracion
from .serializers import DetalleErrorMigracionSerializer, PlantillaMigracionSerializer, ProcesoMigracionSerializer


class PlantillaMigracionViewSet(BaseModelViewSet):
    queryset = PlantillaMigracion.objects.all()
    serializer_class = PlantillaMigracionSerializer


class ProcesoMigracionViewSet(BaseModelViewSet):
    queryset = ProcesoMigracion.objects.all()
    serializer_class = ProcesoMigracionSerializer


class DetalleErrorMigracionViewSet(BaseModelViewSet):
    queryset = DetalleErrorMigracion.objects.all()
    serializer_class = DetalleErrorMigracionSerializer
