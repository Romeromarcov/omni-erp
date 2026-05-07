from rest_framework import viewsets
from .models import Proveedor, ContactoProveedor, CuentaBancariaProveedor
from .serializers import ProveedorSerializer, ContactoProveedorSerializer, CuentaBancariaProveedorSerializer
from apps.core.viewsets import BaseModelViewSet

class ProveedorViewSet(BaseModelViewSet):
    queryset = Proveedor.objects.all()
    serializer_class = ProveedorSerializer

class ContactoProveedorViewSet(BaseModelViewSet):
    queryset = ContactoProveedor.objects.all()
    serializer_class = ContactoProveedorSerializer

class CuentaBancariaProveedorViewSet(BaseModelViewSet):
    queryset = CuentaBancariaProveedor.objects.all()
    serializer_class = CuentaBancariaProveedorSerializer
