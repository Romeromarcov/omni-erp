from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from . import models, serializers


def _empresas(request):
    return get_empresas_visible(request.user)


class CostoProduccionViewSet(BaseModelViewSet):
    queryset = models.CostoProduccion.objects.all()
    serializer_class = serializers.CostoProduccionSerializer

    def get_queryset(self):
        # R-CODE-1
        return models.CostoProduccion.objects.filter(id_empresa__in=_empresas(self.request))


class CostoEstandarProductoViewSet(BaseModelViewSet):
    queryset = models.CostoEstandarProducto.objects.all()
    serializer_class = serializers.CostoEstandarProductoSerializer

    def get_queryset(self):
        # R-CODE-1
        return models.CostoEstandarProducto.objects.filter(id_empresa__in=_empresas(self.request))


class AnalisisVariacionCostoViewSet(BaseModelViewSet):
    queryset = models.AnalisisVariacionCosto.objects.all()
    serializer_class = serializers.AnalisisVariacionCostoSerializer

    def get_queryset(self):
        # R-CODE-1
        return models.AnalisisVariacionCosto.objects.filter(id_empresa__in=_empresas(self.request))
