
from rest_framework import viewsets
from .models import Cliente, ContactoCliente, DireccionCliente
from .serializers import ClienteSerializer, ContactoClienteSerializer, DireccionClienteSerializer
from apps.core.viewsets import BaseModelViewSet

class ClienteViewSet(BaseModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer

    def get_queryset(self):
        queryset = Cliente.objects.all()
        empresa_id = self.request.query_params.get('empresa')
        if empresa_id:
            queryset = queryset.filter(id_empresa=empresa_id)
        return queryset

class ContactoClienteViewSet(BaseModelViewSet):
    queryset = ContactoCliente.objects.all()
    serializer_class = ContactoClienteSerializer

class DireccionClienteViewSet(BaseModelViewSet):
    queryset = DireccionCliente.objects.all()
    serializer_class = DireccionClienteSerializer
