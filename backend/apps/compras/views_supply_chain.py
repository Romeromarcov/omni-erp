"""Vistas API para Costos en Destino / Landed Costs (Plan 09 Fase 5.1)."""

from __future__ import annotations

from drf_yasg.utils import no_body, swagger_auto_schema
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import domain_error_response
from apps.core.idempotency import idempotent
from apps.core.serializer_mixins import TenantFKScopeMixin
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import (
    ActiveFilterMixin,
    EmpresaInjectMixin,
    NulSafeFilterMixin,
    filtrar_ambito_queryset,
    get_empresas_visible,
    validar_uuid_param,
)

from .models import CostoDestino, LineaCostoDestino
from .serializers_supply_chain import CostoDestinoSerializer, LineaCostoDestinoSerializer
from .services_supply_chain import SupplyChainCompraError, anular_costo_destino, aplicar_costo_destino


class CostoDestinoViewSet(
    TenantFKScopeMixin, NulSafeFilterMixin, ActiveFilterMixin, EmpresaInjectMixin, viewsets.ModelViewSet
):
    queryset = CostoDestino.objects.all()
    serializer_class = CostoDestinoSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["numero_documento", "nro_expediente_impor", "nro_planilla_impor", "observaciones"]
    ordering_fields = ["fecha", "numero_documento", "monto_total", "estado", "fecha_creacion"]
    ordering = ["-fecha", "-fecha_creacion"]

    def get_queryset(self):
        qs = (
            CostoDestino.objects.filter(id_empresa__in=get_empresas_visible(self.request.user))
            .select_related("id_recepcion", "id_asiento")
            .prefetch_related("lineas", "asignaciones__id_producto")
        )
        estado = self.request.query_params.get("estado")
        if estado:
            if "\x00" in estado:
                from rest_framework.exceptions import ValidationError

                raise ValidationError({"estado": "Parámetro inválido."})
            qs = qs.filter(estado=estado.strip().upper())
        return filtrar_ambito_queryset(qs, self.request)

    @swagger_auto_schema(request_body=no_body)
    @idempotent(scope="compras:aplicar_costo_destino")
    @action(
        detail=True,
        methods=["post"],
        url_path="aplicar",
        throttle_classes=[*viewsets.ModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def aplicar(self, request, pk=None):
        """Aplica el prorrateo del costo en destino sobre la recepción y revalúa el inventario."""
        costo = self.get_object()
        try:
            res = aplicar_costo_destino(costo, request.user)
        except SupplyChainCompraError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        costo.refresh_from_db()
        return Response(
            {
                "costo_destino": CostoDestinoSerializer(costo, context={"request": request}).data,
                "monto_total": str(res["monto_total"]),
                "productos_revaluados": res["productos_revaluados"],
                "asiento_id": res["asiento_id"],
            },
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(request_body=no_body)
    @action(
        detail=True,
        methods=["post"],
        url_path="anular",
        throttle_classes=[*viewsets.ModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def anular(self, request, pk=None):
        """Anula un costo en destino en BORRADOR."""
        costo = self.get_object()
        try:
            anulado = anular_costo_destino(costo)
        except SupplyChainCompraError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(CostoDestinoSerializer(anulado, context={"request": request}).data, status=status.HTTP_200_OK)


class LineaCostoDestinoViewSet(
    TenantFKScopeMixin, NulSafeFilterMixin, ActiveFilterMixin, EmpresaInjectMixin, viewsets.ModelViewSet
):
    queryset = LineaCostoDestino.objects.all()
    serializer_class = LineaCostoDestinoSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["concepto", "descripcion"]
    ordering_fields = ["concepto", "monto", "fecha_creacion"]
    ordering = ["-fecha_creacion"]

    def get_queryset(self):
        qs = LineaCostoDestino.objects.filter(id_empresa__in=get_empresas_visible(self.request.user)).select_related(
            "id_costo_destino", "id_factura_compra"
        )
        costo_id = self.request.query_params.get("costo_destino")
        if costo_id:
            qs = qs.filter(id_costo_destino_id=validar_uuid_param(costo_id, "costo_destino"))
        return qs
