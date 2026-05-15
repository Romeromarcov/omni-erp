from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import ContactoProveedor, CuentaBancariaProveedor, Proveedor
from .serializers import ContactoProveedorSerializer, CuentaBancariaProveedorSerializer, ProveedorSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class ProveedorViewSet(BaseModelViewSet):
    queryset = Proveedor.objects.all()
    serializer_class = ProveedorSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar por empresas visibles del usuario autenticado
        return Proveedor.objects.filter(id_empresa__in=_empresas(self.request)).order_by("razon_social")


class ContactoProveedorViewSet(BaseModelViewSet):
    queryset = ContactoProveedor.objects.all()
    serializer_class = ContactoProveedorSerializer


class CuentaBancariaProveedorViewSet(BaseModelViewSet):
    queryset = CuentaBancariaProveedor.objects.all()
    serializer_class = CuentaBancariaProveedorSerializer
