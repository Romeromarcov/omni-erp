from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from . import models, serializers
from apps.core.viewsets import BaseModelViewSet

class DespachoViewSet(BaseModelViewSet):
    queryset = models.Despacho.objects.all()
    serializer_class = serializers.DespachoSerializer

class DetalleDespachoViewSet(BaseModelViewSet):
    queryset = models.DetalleDespacho.objects.all()
    serializer_class = serializers.DetalleDespachoSerializer
