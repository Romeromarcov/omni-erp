from rest_framework import viewsets
from .models import ConfiguracionIntegracion, LogIntegracion, MapeoCampo
from .serializers import ConfiguracionIntegracionSerializer, LogIntegracionSerializer, MapeoCampoSerializer
from apps.core.viewsets import BaseModelViewSet

class ConfiguracionIntegracionViewSet(BaseModelViewSet):
    queryset = ConfiguracionIntegracion.objects.all()
    serializer_class = ConfiguracionIntegracionSerializer

class LogIntegracionViewSet(BaseModelViewSet):
    queryset = LogIntegracion.objects.all()
    serializer_class = LogIntegracionSerializer

class MapeoCampoViewSet(BaseModelViewSet):
    queryset = MapeoCampo.objects.all()
    serializer_class = MapeoCampoSerializer
