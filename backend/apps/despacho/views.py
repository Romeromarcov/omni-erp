from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from . import models, serializers


def _empresas(request):
    return get_empresas_visible(request.user)


class DespachoViewSet(BaseModelViewSet):
    queryset = models.Despacho.objects.all()
    serializer_class = serializers.DespachoSerializer

    def get_queryset(self):
        # R-CODE-1
        return models.Despacho.objects.filter(id_empresa__in=_empresas(self.request))


class DetalleDespachoViewSet(BaseModelViewSet):
    queryset = models.DetalleDespacho.objects.all()
    serializer_class = serializers.DetalleDespachoSerializer

    def get_queryset(self):
        # R-CODE-1 — DetalleDespacho no tiene id_empresa directo; llega via id_despacho→Despacho
        return models.DetalleDespacho.objects.filter(id_despacho__id_empresa__in=_empresas(self.request))
