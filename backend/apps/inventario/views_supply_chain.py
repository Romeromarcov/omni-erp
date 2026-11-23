"""Vistas API para Conteo Físico Cíclico/Total Dual (Plan 09 Fase 5.3)."""

from __future__ import annotations

from drf_yasg.utils import no_body, swagger_auto_schema
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.almacenes.models import Almacen, UbicacionAlmacen
from apps.core.exceptions import domain_error_response
from apps.core.idempotency import idempotent
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import (
    ActiveFilterMixin,
    NulSafeFilterMixin,
    filtrar_ambito_queryset,
    get_empresas_visible,
)

from .models import ConteoInventario, Producto, VarianteProducto
from .serializers_supply_chain import (
    ConteoInventarioSerializer,
    CrearConteoInventarioInputSerializer,
    EscanearConteoInputSerializer,
    LineaConteoInventarioSerializer,
    resolver_empresa_usuario_inventario,
)
from .services_supply_chain import (
    InventarioSupplyChainError,
    anular_conteo,
    aprobar_aplicar_conteo,
    crear_conteo_inventario,
    enviar_conteo_aprobacion,
    registrar_escaneo_conteo,
)


class ConteoInventarioViewSet(NulSafeFilterMixin, ActiveFilterMixin, viewsets.ModelViewSet):
    queryset = ConteoInventario.objects.all()
    serializer_class = ConteoInventarioSerializer
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["numero", "id_almacen__nombre_almacen", "observaciones"]
    ordering_fields = ["fecha_conteo", "numero", "estado", "fecha_creacion"]
    ordering = ["-fecha_conteo", "-fecha_creacion"]

    def get_queryset(self):
        qs = (
            ConteoInventario.objects.filter(id_empresa__in=get_empresas_visible(self.request.user))
            .select_related("id_almacen", "id_responsable", "id_aprobador")
            .prefetch_related("lineas__id_producto")
        )
        estado = self.request.query_params.get("estado")
        if estado:
            if "\x00" in estado:
                from rest_framework.exceptions import ValidationError

                raise ValidationError({"estado": "Parámetro inválido."})
            qs = qs.filter(estado=estado.strip().upper())
        return filtrar_ambito_queryset(qs, self.request)

    @swagger_auto_schema(request_body=CrearConteoInventarioInputSerializer)
    def create(self, request, *args, **kwargs):
        ser = CrearConteoInventarioInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        empresa = resolver_empresa_usuario_inventario(request, request.data.get("id_empresa"))

        almacen = Almacen.objects.filter(pk=vd["id_almacen"], id_empresa=empresa).first()
        if almacen is None:
            return Response({"id_almacen": "Almacén no encontrado en la empresa."}, status=status.HTTP_404_NOT_FOUND)

        items_resueltos = []
        for it in vd.get("items") or []:
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
                        {"items": f"Variante {it['variante']} inválida para el producto."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            ubic = None
            if it.get("ubicacion"):
                ubic = UbicacionAlmacen.objects.filter(
                    pk=it["ubicacion"], id_empresa=empresa, id_almacen=almacen
                ).first()
                if ubic is None:
                    return Response(
                        {"items": f"Ubicación {it['ubicacion']} no pertenece al almacén."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            items_resueltos.append({"producto": prod, "variante": var, "ubicacion": ubic})

        try:
            conteo = crear_conteo_inventario(
                empresa=empresa,
                almacen=almacen,
                responsable=request.user,
                tipo_conteo=vd["tipo_conteo"],
                ambito=vd["ambito"],
                fecha_conteo=vd.get("fecha_conteo"),
                numero=vd.get("numero"),
                observaciones=vd.get("observaciones", ""),
                items=items_resueltos or None,
            )
        except InventarioSupplyChainError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        return Response(
            ConteoInventarioSerializer(conteo, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @swagger_auto_schema(request_body=EscanearConteoInputSerializer)
    @action(
        detail=True,
        methods=["post"],
        url_path="escanear",
        throttle_classes=[*viewsets.ModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def escanear(self, request, pk=None):
        """Registra escaneo de código de barras / SKU durante la captura física."""
        conteo = self.get_object()
        ser = EscanearConteoInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        try:
            linea = registrar_escaneo_conteo(
                conteo=conteo,
                codigo_o_producto_id=vd["codigo"],
                cantidad=vd["cantidad"],
                modo=vd["modo"],
                variante_id=str(vd["variante"]) if vd.get("variante") else None,
                ubicacion_id=str(vd["ubicacion"]) if vd.get("ubicacion") else None,
                observaciones=vd.get("observaciones", ""),
            )
        except InventarioSupplyChainError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(LineaConteoInventarioSerializer(linea).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(request_body=no_body)
    @action(
        detail=True,
        methods=["post"],
        url_path="enviar-aprobacion",
        throttle_classes=[*viewsets.ModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def enviar_aprobacion(self, request, pk=None):
        """Finaliza captura y deja el conteo en PENDIENTE_APROBACION."""
        conteo = self.get_object()
        try:
            upd = enviar_conteo_aprobacion(conteo)
        except InventarioSupplyChainError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(ConteoInventarioSerializer(upd, context={"request": request}).data)

    @swagger_auto_schema(request_body=no_body)
    @idempotent(scope="inventario:aprobar_aplicar_conteo")
    @action(
        detail=True,
        methods=["post"],
        url_path="aprobar-aplicar",
        throttle_classes=[*viewsets.ModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def aprobar_aplicar(self, request, pk=None):
        """Aprueba diferencias y dispara los ajustes de inventario con ámbito del conteo."""
        conteo = self.get_object()
        try:
            res = aprobar_aplicar_conteo(conteo, request.user)
        except InventarioSupplyChainError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        conteo.refresh_from_db()
        return Response(
            {
                "conteo": ConteoInventarioSerializer(conteo, context={"request": request}).data,
                "ajustes_generados": res["ajustes_generados"],
                "movimientos_ids": res["movimientos_ids"],
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
        """Anula un conteo aún no aplicado."""
        conteo = self.get_object()
        try:
            upd = anular_conteo(conteo)
        except InventarioSupplyChainError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(ConteoInventarioSerializer(upd, context={"request": request}).data)
