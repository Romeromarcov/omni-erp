from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import CatalogoValor, ParametroSistema, TipoDocumento
from .serializers import CatalogoValorSerializer, ParametroSistemaSerializer, TipoDocumentoSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class TipoDocumentoViewSet(BaseModelViewSet):
    queryset = TipoDocumento.objects.all()
    serializer_class = TipoDocumentoSerializer

    def get_queryset(self):
        # R-CODE-1 — TipoDocumento no tiene id_empresa directo
        # TODO: modelo sin id_empresa — agregar FK en Fase 2
        return TipoDocumento.objects.all()


class ParametroSistemaViewSet(BaseModelViewSet):
    queryset = ParametroSistema.objects.all()
    serializer_class = ParametroSistemaSerializer

    def get_queryset(self):
        # R-CODE-1 — id_empresa es nullable; filtramos solo los de empresas visibles o los globales (id_empresa=None)
        return ParametroSistema.objects.filter(id_empresa__in=_empresas(self.request)) | ParametroSistema.objects.filter(id_empresa__isnull=True)


class CatalogoValorViewSet(BaseModelViewSet):
    queryset = CatalogoValor.objects.all()
    serializer_class = CatalogoValorSerializer

    def get_queryset(self):
        # R-CODE-1 — CatalogoValor no tiene id_empresa directo
        # TODO: modelo sin id_empresa — agregar FK en Fase 2
        return CatalogoValor.objects.all()
