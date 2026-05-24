from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import CuentaBancariaEmpresa
from .serializers import CuentaBancariaEmpresaSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class CuentaBancariaEmpresaViewSet(BaseModelViewSet):
    queryset = CuentaBancariaEmpresa.objects.all()
    serializer_class = CuentaBancariaEmpresaSerializer

    def get_queryset(self):
        # R-CODE-1 — el campo FK a empresa es "empresa" (no "id_empresa")
        return CuentaBancariaEmpresa.objects.filter(empresa__in=_empresas(self.request))
