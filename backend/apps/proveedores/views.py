from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import ContactoProveedor, CuentaBancariaProveedor, Proveedor
from .serializers import ContactoProveedorSerializer, CuentaBancariaProveedorSerializer, ProveedorSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class ProveedorViewSet(BaseModelViewSet):
    queryset = Proveedor.objects.all()
    serializer_class = ProveedorSerializer

    def get_queryset(self):
        return Proveedor.objects.filter(id_empresa__in=_empresas(self.request)).order_by("razon_social")

    @action(detail=False, methods=["get"], url_path="buscar-por-rif")
    def buscar_por_rif(self, request):
        """GET /api/proveedores/proveedores/buscar-por-rif/?rif=J-12345678"""
        rif = request.query_params.get("rif", "").strip()
        if not rif:
            return Response({"error": "Parámetro 'rif' requerido."}, status=status.HTTP_400_BAD_REQUEST)
        qs = self.get_queryset().filter(rif__icontains=rif)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class ContactoProveedorViewSet(BaseModelViewSet):
    queryset = ContactoProveedor.objects.all()
    serializer_class = ContactoProveedorSerializer


class CuentaBancariaProveedorViewSet(BaseModelViewSet):
    queryset = CuentaBancariaProveedor.objects.all()
    serializer_class = CuentaBancariaProveedorSerializer
