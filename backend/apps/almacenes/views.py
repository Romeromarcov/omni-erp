from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import Almacen, UbicacionAlmacen
from .serializers import AlmacenSerializer, UbicacionAlmacenSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class AlmacenViewSet(BaseModelViewSet):
    queryset = Almacen.objects.all()
    serializer_class = AlmacenSerializer

    def get_queryset(self):
        # R-CODE-1
        return Almacen.objects.filter(id_empresa__in=_empresas(self.request))


class UbicacionAlmacenViewSet(BaseModelViewSet):
    queryset = UbicacionAlmacen.objects.all()
    serializer_class = UbicacionAlmacenSerializer

    def get_queryset(self):
        # R-CODE-1
        return UbicacionAlmacen.objects.filter(id_empresa__in=_empresas(self.request))
