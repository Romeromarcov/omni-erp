from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import ConfiguracionIntegracion, LogIntegracion, MapeoCampo
from .serializers import ConfiguracionIntegracionSerializer, LogIntegracionSerializer, MapeoCampoSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class ConfiguracionIntegracionViewSet(BaseModelViewSet):
    queryset = ConfiguracionIntegracion.objects.all()
    serializer_class = ConfiguracionIntegracionSerializer

    def get_queryset(self):
        # R-CODE-1
        return ConfiguracionIntegracion.objects.filter(id_empresa__in=_empresas(self.request))


class LogIntegracionViewSet(BaseModelViewSet):
    queryset = LogIntegracion.objects.all()
    serializer_class = LogIntegracionSerializer

    def get_queryset(self):
        # R-CODE-1 — LogIntegracion llega via id_configuracion→ConfiguracionIntegracion
        return LogIntegracion.objects.filter(id_configuracion__id_empresa__in=_empresas(self.request))


class MapeoCampoViewSet(BaseModelViewSet):
    queryset = MapeoCampo.objects.all()
    serializer_class = MapeoCampoSerializer

    def get_queryset(self):
        # R-CODE-1 — MapeoCampo llega via id_configuracion_integracion→ConfiguracionIntegracion
        return MapeoCampo.objects.filter(id_configuracion_integracion__id_empresa__in=_empresas(self.request))
