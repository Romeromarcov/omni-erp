from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import Cliente, ContactoCliente, DireccionCliente
from .serializers import ClienteSerializer, ContactoClienteSerializer, DireccionClienteSerializer


class ClienteViewSet(BaseModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar SIEMPRE por las empresas visibles del usuario autenticado.
        # Nunca devolver clientes de empresas ajenas.
        empresas = get_empresas_visible(self.request.user)
        return Cliente.objects.filter(id_empresa__in=empresas)


class ContactoClienteViewSet(BaseModelViewSet):
    queryset = ContactoCliente.objects.all()
    serializer_class = ContactoClienteSerializer


class DireccionClienteViewSet(BaseModelViewSet):
    queryset = DireccionCliente.objects.all()
    serializer_class = DireccionClienteSerializer
