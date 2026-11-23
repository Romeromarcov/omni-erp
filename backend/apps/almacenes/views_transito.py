"""Vistas API para Transferencias Inter-Almacén en Tránsito (Plan 09 Fase 5.4)."""

from __future__ import annotations

from drf_yasg.utils import no_body, swagger_auto_schema
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.exceptions import domain_error_response
from apps.core.idempotency import idempotent
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import (
    ActiveFilterMixin,
    NulSafeFilterMixin,
    filtrar_ambito_queryset,
    get_empresa_primaria,
    get_empresas_visible,
)
from apps.inventario.models import Producto, VarianteProducto

from .models import Almacen, TransferenciaTransito, UbicacionAlmacen
from .serializers_transito import (
    DespacharTransferenciaTransitoInputSerializer,
    RecibirTransferenciaTransitoInputSerializer,
    TransferenciaTransitoSerializer,
)
from .services_transito import (
    TransferenciaTransitoError,
    cancelar_transferencia_transito,
    despachar_transferencia_transito,
    recibir_transferencia_transito,
)


class TransferenciaTransitoViewSet(NulSafeFilterMixin, ActiveFilterMixin, viewsets.ReadOnlyModelViewSet):
    queryset = TransferenciaTransito.objects.all()
    serializer_class = TransferenciaTransitoSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["numero", "id_almacen_origen__nombre_almacen", "id_almacen_destino__nombre_almacen"]
    ordering_fields = ["fecha_despacho", "fecha_recepcion", "numero", "estado", "fecha_creacion"]
    ordering = ["-fecha_despacho", "-fecha_creacion"]

    def get_queryset(self):
        qs = (
            TransferenciaTransito.objects.filter(id_empresa__in=get_empresas_visible(self.request.user))
            .select_related("id_almacen_origen", "id_almacen_destino", "id_ubicacion_transito")
            .prefetch_related("detalles__id_producto")
        )
        estado = self.request.query_params.get("estado")
        if estado:
            if "\x00" in estado:
                raise ValidationError({"estado": "Parámetro inválido."})
            qs = qs.filter(estado=estado.strip().upper())
        return filtrar_ambito_queryset(qs, self.request)

    @swagger_auto_schema(request_body=DespacharTransferenciaTransitoInputSerializer)
    @idempotent(scope="almacenes:despachar_transito")
    @action(
        detail=False,
        methods=["post"],
        url_path="despachar",
        throttle_classes=[*viewsets.ReadOnlyModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def despachar(self, request):
        """Despacha mercancía desde el almacén origen dejándola EN_TRANSITO."""
        ser = DespacharTransferenciaTransitoInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data

        visibles = get_empresas_visible(request.user)
        raw_emp = request.data.get("id_empresa")
        if raw_emp:
            empresa = visibles.filter(pk=raw_emp).first()
            if empresa is None:
                raise ValidationError({"id_empresa": "Empresa fuera de su alcance."})
        else:
            empresa = get_empresa_primaria(request.user) or visibles.first()
            if empresa is None:
                raise ValidationError({"id_empresa": "Usuario sin empresa asignada."})

        alm_orig = Almacen.objects.filter(pk=vd["id_almacen_origen"], id_empresa=empresa).first()
        alm_dest = Almacen.objects.filter(pk=vd["id_almacen_destino"], id_empresa=empresa).first()
        if alm_orig is None or alm_dest is None:
            return Response({"detail": "Almacén de origen o destino no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        ubic = None
        if vd.get("id_ubicacion_transito"):
            ubic = UbicacionAlmacen.objects.filter(pk=vd["id_ubicacion_transito"], id_empresa=empresa).first()
            if ubic is None:
                return Response(
                    {"id_ubicacion_transito": "Ubicación de tránsito no encontrada."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        items_resueltos = []
        for it in vd["items"]:
            prod = Producto.objects.filter(pk=it["producto"], id_empresa=empresa).first()
            if prod is None:
                return Response(
                    {"items": f"Producto {it['producto']} no encontrado en la empresa."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            var = None
            if it.get("variante"):
                var = VarianteProducto.objects.filter(pk=it["variante"], id_producto=prod).first()
                if var is None:
                    return Response(
                        {"items": f"Variante {it['variante']} no corresponde al producto."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            items_resueltos.append({"producto": prod, "variante": var, "cantidad": it["cantidad"]})

        try:
            trans = despachar_transferencia_transito(
                empresa=empresa,
                almacen_origen=alm_orig,
                almacen_destino=alm_dest,
                usuario=request.user,
                items=items_resueltos,
                ubicacion_transito=ubic,
                ambito=vd["ambito"],
                numero=vd.get("numero"),
                observaciones=vd.get("observaciones", ""),
            )
        except TransferenciaTransitoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        return Response(
            TransferenciaTransitoSerializer(trans, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @swagger_auto_schema(request_body=RecibirTransferenciaTransitoInputSerializer)
    @idempotent(scope="almacenes:recibir_transito")
    @action(
        detail=True,
        methods=["post"],
        url_path="recibir",
        throttle_classes=[*viewsets.ReadOnlyModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def recibir(self, request, pk=None):
        """Recibe en almacén destino una transferencia EN_TRANSITO (total o parcial)."""
        trans = self.get_object()
        ser = RecibirTransferenciaTransitoInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        try:
            res = recibir_transferencia_transito(
                transferencia=trans,
                usuario=request.user,
                cantidades_recibidas=vd.get("cantidades_recibidas") or None,
                observaciones=vd.get("observaciones", ""),
            )
        except TransferenciaTransitoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        trans.refresh_from_db()
        return Response(
            {
                "transferencia": TransferenciaTransitoSerializer(trans, context={"request": request}).data,
                "movimientos_entrada": res["movimientos_entrada"],
                "mermas": res["mermas"],
            },
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(request_body=no_body)
    @action(
        detail=True,
        methods=["post"],
        url_path="cancelar",
        throttle_classes=[*viewsets.ReadOnlyModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def cancelar(self, request, pk=None):
        """Cancela una transferencia EN_TRANSITO y devuelve el stock al almacén origen."""
        trans = self.get_object()
        try:
            upd = cancelar_transferencia_transito(trans, request.user)
        except TransferenciaTransitoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(TransferenciaTransitoSerializer(upd, context={"request": request}).data)
