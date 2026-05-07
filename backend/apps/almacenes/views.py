
from rest_framework import viewsets
from .models import Almacen, UbicacionAlmacen
from .serializers import AlmacenSerializer, UbicacionAlmacenSerializer
from apps.core.viewsets import BaseModelViewSet

class AlmacenViewSet(BaseModelViewSet):
    queryset = Almacen.objects.all()
    serializer_class = AlmacenSerializer

class UbicacionAlmacenViewSet(BaseModelViewSet):
    queryset = UbicacionAlmacen.objects.all()
    serializer_class = UbicacionAlmacenSerializer
