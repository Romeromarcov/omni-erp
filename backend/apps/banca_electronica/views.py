from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet

from .models import CuentaBancariaEmpresa
from .serializers import CuentaBancariaEmpresaSerializer


class CuentaBancariaEmpresaViewSet(BaseModelViewSet):
    queryset = CuentaBancariaEmpresa.objects.all()
    serializer_class = CuentaBancariaEmpresaSerializer
