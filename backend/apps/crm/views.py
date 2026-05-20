from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import Cliente, ContactoCliente, DireccionCliente
from .serializers import ClienteSerializer, ContactoClienteSerializer, DireccionClienteSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class ClienteViewSet(BaseModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer

    def get_queryset(self):
        empresas = _empresas(self.request)
        qs = Cliente.objects.filter(id_empresa__in=empresas)
        empresa_id = self.request.query_params.get("empresa")
        if empresa_id:
            qs = qs.filter(id_empresa=empresa_id)
        return qs

    @action(detail=False, methods=["get"], url_path="buscar-por-rif")
    def buscar_por_rif(self, request):
        """GET /api/crm/clientes/buscar-por-rif/?rif=J-12345678"""
        rif = request.query_params.get("rif", "").strip()
        if not rif:
            return Response({"error": "Parámetro 'rif' requerido."}, status=status.HTTP_400_BAD_REQUEST)
        qs = self.get_queryset().filter(rif__icontains=rif)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="historial-ventas")
    def historial_ventas(self, request, pk=None):
        """GET /api/crm/clientes/{pk}/historial-ventas/"""
        from apps.ventas.models import Pedido
        from apps.ventas.serializers import PedidoSerializer

        cliente = self.get_object()
        pedidos = (
            Pedido.objects.filter(
                id_empresa__in=_empresas(request),
                id_cliente=cliente,
            )
            .select_related("id_empresa")
            .prefetch_related("detalles")
            .order_by("-fecha_pedido")
        )

        return Response(
            {
                "cliente_id": str(cliente.id_cliente),
                "razon_social": cliente.razon_social,
                "rif": cliente.rif,
                "tipo_cliente": cliente.tipo_cliente,
                "limite_credito": str(cliente.limite_credito),
                "dias_credito": cliente.dias_credito,
                "pedidos": PedidoSerializer(pedidos, many=True).data,
            }
        )

    @action(detail=True, methods=["get"], url_path="credito-disponible")
    def credito_disponible(self, request, pk=None):
        """
        GET /api/crm/clientes/{pk}/credito-disponible/
        Devuelve saldo de CxC pendiente y crédito disponible.
        """
        from decimal import Decimal

        from django.db.models import Sum

        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        cliente = self.get_object()
        if cliente.tipo_cliente != "CREDITO":
            return Response({"credito_disponible": None, "detalle": "Cliente de contado."})

        saldo_pendiente = (
            CuentaPorCobrar.objects.filter(
                cliente=cliente,
                empresa__in=_empresas(request),
                estado__in=["pendiente", "parcial", "vencida"],
            ).aggregate(total=Sum("monto"))["total"]
            or Decimal("0")
        )

        disponible = cliente.limite_credito - saldo_pendiente
        return Response(
            {
                "cliente_id": str(cliente.id_cliente),
                "limite_credito": str(cliente.limite_credito),
                "saldo_pendiente": str(saldo_pendiente),
                "credito_disponible": str(max(disponible, Decimal("0"))),
                "bloqueado": disponible < 0,
            }
        )


class ContactoClienteViewSet(BaseModelViewSet):
    queryset = ContactoCliente.objects.all()
    serializer_class = ContactoClienteSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar por empresa a través del FK id_cliente → id_empresa
        return ContactoCliente.objects.filter(id_empresa__in=_empresas(self.request))


class DireccionClienteViewSet(BaseModelViewSet):
    queryset = DireccionCliente.objects.all()
    serializer_class = DireccionClienteSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar por empresa a través del FK id_cliente → id_empresa
        return DireccionCliente.objects.filter(id_empresa__in=_empresas(self.request))
