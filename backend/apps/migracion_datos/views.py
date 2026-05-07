from rest_framework import viewsets
from .models import PlantillaMigracion, ProcesoMigracion, DetalleErrorMigracion
from .serializers import PlantillaMigracionSerializer, ProcesoMigracionSerializer, DetalleErrorMigracionSerializer
from apps.core.viewsets import BaseModelViewSet

class PlantillaMigracionViewSet(BaseModelViewSet):
    queryset = PlantillaMigracion.objects.all()
    serializer_class = PlantillaMigracionSerializer

class ProcesoMigracionViewSet(BaseModelViewSet):
    queryset = ProcesoMigracion.objects.all()
    serializer_class = ProcesoMigracionSerializer

class DetalleErrorMigracionViewSet(BaseModelViewSet):
    queryset = DetalleErrorMigracion.objects.all()
    serializer_class = DetalleErrorMigracionSerializer
