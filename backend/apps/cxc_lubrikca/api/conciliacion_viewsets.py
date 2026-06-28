"""ViewSets de conciliación CxC Lubrikca (Fase 4).

Tenant-scoped (mismo patrón que la config de Fase 1 / operación de Fase 3):
- ``ConfiguracionConciliacionViewSet`` — CRUD de tolerancias del semáforo.
- ``ConciliacionLubrikcaViewSet`` — lectura del resultado + acciones
  ``conciliar`` (corre el motor sobre un pedido), ``revisar`` (marca revisado)
  y ``resumen`` (tablero de cartera de la empresa).
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
    ConciliacionLubrikca,
    ConfiguracionConciliacion,
    PedidoLubrikca,
)
from apps.cxc_lubrikca.services.conciliacion import (
    ConciliacionError,
    conciliar_pedido,
    marcar_revisado,
    resumen_cartera,
)

from .conciliacion_serializers import (
    ConciliarSerializer,
    ConciliacionLubrikcaSerializer,
    ConfiguracionConciliacionSerializer,
)


class ConfiguracionConciliacionViewSet(SoftDeleteModelMixin, BaseModelViewSet):
    """CRUD de tolerancias del semáforo (scope multi-tenant)."""

    model = ConfiguracionConciliacion
    queryset = ConfiguracionConciliacion.objects.all()
    serializer_class = ConfiguracionConciliacionSerializer
    search_fields = []
    ordering_fields = ["created_at", "tolerance_rounding", "tolerance_red"]

    def get_queryset(self):
        return ConfiguracionConciliacion.objects.filter(
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


class ConciliacionLubrikcaViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Lectura de conciliaciones + acciones ``conciliar`` / ``revisar`` / ``resumen``."""

    model = ConciliacionLubrikca
    queryset = ConciliacionLubrikca.objects.all()
    serializer_class = ConciliacionLubrikcaSerializer
    search_fields = []
    ordering_fields = ["conciliado_en", "diferencia", "resultado"]

    def get_queryset(self):
        return ConciliacionLubrikca.objects.filter(
            empresa__in=get_empresas_visible(self.request.user),
            deleted_at__isnull=True,
        )

    def _empresa_usuario(self):
        empresa = get_empresas_visible(self.request.user).first()
        if empresa is None:
            raise PermissionDenied("El usuario no tiene una empresa asignada.")
        return empresa

    @action(detail=False, methods=["post"])
    def conciliar(self, request):
        """Corre el motor de conciliación sobre un pedido del tenant."""
        body = ConciliarSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        empresa = self._empresa_usuario()

        try:
            pedido = PedidoLubrikca.objects.get(
                id=body.validated_data["pedido"],
                empresa=empresa,
                deleted_at__isnull=True,
            )
        except PedidoLubrikca.DoesNotExist:
            return Response(
                {"pedido": "No encontrado para esta empresa."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            conciliacion = conciliar_pedido(pedido)
        except ConciliacionError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            ConciliacionLubrikcaSerializer(conciliacion).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def revisar(self, request, pk=None):
        """Marca quién revisó la conciliación."""
        conciliacion = self.get_object()
        marcar_revisado(conciliacion, request.user)
        conciliacion.refresh_from_db()
        return Response(ConciliacionLubrikcaSerializer(conciliacion).data)

    @action(detail=False, methods=["get"])
    def resumen(self, request):
        """Tablero de cartera de la empresa del usuario."""
        empresa = self._empresa_usuario()
        return Response(resumen_cartera(empresa))
