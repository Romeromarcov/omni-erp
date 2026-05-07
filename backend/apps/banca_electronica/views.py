from rest_framework import viewsets
from .models import CuentaBancariaEmpresa
from .serializers import CuentaBancariaEmpresaSerializer
from apps.core.viewsets import BaseModelViewSet

class CuentaBancariaEmpresaViewSet(BaseModelViewSet):
    queryset = CuentaBancariaEmpresa.objects.all()
    serializer_class = CuentaBancariaEmpresaSerializer
