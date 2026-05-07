from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from . import models, serializers
from apps.core.viewsets import BaseModelViewSet

class CostoProduccionViewSet(BaseModelViewSet):
    queryset = models.CostoProduccion.objects.all()
    serializer_class = serializers.CostoProduccionSerializer

class CostoEstandarProductoViewSet(BaseModelViewSet):
    queryset = models.CostoEstandarProducto.objects.all()
    serializer_class = serializers.CostoEstandarProductoSerializer

class AnalisisVariacionCostoViewSet(BaseModelViewSet):
    queryset = models.AnalisisVariacionCosto.objects.all()
    serializer_class = serializers.AnalisisVariacionCostoSerializer
