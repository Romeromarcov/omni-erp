"""ViewSets de operación CxC Lubrikca (Fase 3).

Tenant-scoped (mismo patrón que la config de Fase 1): el queryset se acota a las
empresas visibles del usuario y excluye soft-deleted; ``perform_create`` fuerza
la empresa. Las vinculaciones y la bandeja exponen las acciones del cierre
híbrido (registrar / recalcular / proponer / confirmar).
"""

from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.viewsets import (
    BaseModelViewSet,
    SoftDeleteModelMixin,
    get_empresas_visible,
)
from apps.cxc_lubrikca.models import (
    BandejaFacturacion,
    LineaPedidoLubrikca,
    PagoLubrikca,
    PedidoLubrikca,
    PrecioListaLubrikca,
    Vinculacion,
)
from apps.cxc_lubrikca.services.aprobacion import confirmar_cierre, proponer_cierre
from apps.cxc_lubrikca.services.bridge import BridgeError, recalcular_bandeja
from apps.cxc_lubrikca.services.captura import (
    VinculacionError,
    registrar_vinculacion,
)

from .operacion_serializers import (
    BandejaFacturacionSerializer,
    ConfirmarCierreSerializer,
    LineaPedidoLubrikcaSerializer,
    PagoLubrikcaSerializer,
    PedidoLubrikcaSerializer,
    PrecioListaLubrikcaSerializer,
    RegistrarVinculacionSerializer,
    VinculacionSerializer,
)


class _CxcLubrikcaTenantViewSet(SoftDeleteModelMixin, BaseModelViewSet):
    """Base CRUD tenant-scoped (idéntico a la config de Fase 1)."""

    model = None

    def get_queryset(self):
        return self.model.objects.filter(
            empresa__in=get_empresas_visible(self.request.user),
            deleted_at__isnull=True,
        )

    def _empresa_usuario(self):
        empresa = get_empresas_visible(self.request.user).first()
        if empresa is None:
            raise PermissionDenied("El usuario no tiene una empresa asignada.")
        return empresa

    def perform_create(self, serializer):
        serializer.save(empresa=self._empresa_usuario())


class PedidoLubrikcaViewSet(_CxcLubrikcaTenantViewSet):
    model = PedidoLubrikca
    queryset = PedidoLubrikca.objects.all()
    serializer_class = PedidoLubrikcaSerializer
    search_fields = ["so_id", "cliente_externo_id", "cliente_nombre", "vendedor_email"]
    ordering_fields = ["fecha", "fecha_entrega", "so_id", "monto_total"]

    @action(detail=True, methods=["post"])
    def recalcular(self, request, pk=None):
        """Recalcula y persiste la bandeja del pedido."""
        pedido = self.get_object()
        try:
            bandeja = recalcular_bandeja(pedido)
        except BridgeError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(BandejaFacturacionSerializer(bandeja).data)


class LineaPedidoLubrikcaViewSet(_CxcLubrikcaTenantViewSet):
    model = LineaPedidoLubrikca
    queryset = LineaPedidoLubrikca.objects.all()
    serializer_class = LineaPedidoLubrikcaSerializer
    search_fields = ["producto", "marca", "categoria", "linea_id"]
    ordering_fields = ["linea_id", "producto", "cantidad", "precio_unitario"]


class PrecioListaLubrikcaViewSet(_CxcLubrikcaTenantViewSet):
    model = PrecioListaLubrikca
    queryset = PrecioListaLubrikca.objects.all()
    serializer_class = PrecioListaLubrikcaSerializer
    search_fields = ["producto", "lista"]
    ordering_fields = ["producto", "lista", "precio"]


class PagoLubrikcaViewSet(_CxcLubrikcaTenantViewSet):
    model = PagoLubrikca
    queryset = PagoLubrikca.objects.all()
    serializer_class = PagoLubrikcaSerializer
    search_fields = ["pago_id", "cliente_externo_id", "metodo_pago", "vendedor_email"]
    ordering_fields = ["fecha_pago", "monto", "pago_id"]


class VinculacionViewSet(
    SoftDeleteModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Lectura de vinculaciones + acción ``registrar`` (servicio de captura).

    No expone create/update planos: los campos congelados (tasas, equivalentes)
    se estampan en el servicio, nunca por la API.
    """

    model = Vinculacion
    queryset = Vinculacion.objects.all()
    serializer_class = VinculacionSerializer
    search_fields = []
    ordering_fields = ["created_at", "monto_aplicado", "estado"]

    def get_queryset(self):
        return Vinculacion.objects.filter(
            empresa__in=get_empresas_visible(self.request.user),
            deleted_at__isnull=True,
        )

    def _empresa_usuario(self):
        empresa = get_empresas_visible(self.request.user).first()
        if empresa is None:
            raise PermissionDenied("El usuario no tiene una empresa asignada.")
        return empresa

    @action(detail=False, methods=["post"])
    def registrar(self, request):
        body = RegistrarVinculacionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        empresa = self._empresa_usuario()

        # Resolver pedido y pago dentro del tenant (404 si son de otra empresa).
        try:
            pedido = PedidoLubrikca.objects.get(
                id=data["pedido"], empresa=empresa, deleted_at__isnull=True
            )
        except PedidoLubrikca.DoesNotExist:
            return Response(
                {"pedido": "No encontrado para esta empresa."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            pago = PagoLubrikca.objects.get(
                id=data["pago"], empresa=empresa, deleted_at__isnull=True
            )
        except PagoLubrikca.DoesNotExist:
            return Response(
                {"pago": "No encontrado para esta empresa."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            vinc = registrar_vinculacion(
                pedido=pedido,
                pago=pago,
                monto_aplicado=data["monto_aplicado"],
                hora_pago_confirmada=data["hora_pago_confirmada"],
                usuario=request.user,
                es_tasa_heredada=data["es_tasa_heredada"],
            )
        except (VinculacionError, BridgeError) as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            VinculacionSerializer(vinc).data, status=status.HTTP_201_CREATED
        )


class BandejaFacturacionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Bandeja de solo lectura + acciones del cierre híbrido."""

    model = BandejaFacturacion
    queryset = BandejaFacturacion.objects.all()
    serializer_class = BandejaFacturacionSerializer
    search_fields = []
    ordering_fields = ["calculado_en", "total_motor", "estado"]

    def get_queryset(self):
        return BandejaFacturacion.objects.filter(
            empresa__in=get_empresas_visible(self.request.user),
            deleted_at__isnull=True,
        )

    @action(detail=True, methods=["post"])
    def proponer(self, request, pk=None):
        bandeja = self.get_object()
        try:
            solicitud = proponer_cierre(bandeja, request.user)
        except VinculacionError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        if solicitud is None:
            return Response(
                {
                    "detail": "No requiere aprobación según el flujo configurado.",
                    "solicitud": None,
                }
            )
        return Response({"solicitud": str(solicitud.pk)})

    @action(detail=True, methods=["post"])
    def confirmar(self, request, pk=None):
        bandeja = self.get_object()
        body = ConfirmarCierreSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        from apps.gestion_aprobaciones.services import AprobacionError

        try:
            confirmar_cierre(
                bandeja,
                request.user,
                aprobado=body.validated_data["aprobado"],
                comentarios=body.validated_data["comentarios"],
            )
        except (VinculacionError, AprobacionError) as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        bandeja.refresh_from_db()
        return Response(BandejaFacturacionSerializer(bandeja).data)
