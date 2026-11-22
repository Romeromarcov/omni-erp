from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import domain_error_response
from apps.core.viewsets import (
    BaseModelViewSet,
    EmpresaInjectMixin,
    NulSafeFilterMixin,
    get_empresas_visible,
    validar_uuid_param,
)
from apps.inventario.models import Producto, VarianteProducto

from .models import Almacen, StockUbicacion, UbicacionAlmacen
from .serializers import (
    AlmacenSerializer,
    ReservarUbicacionInputSerializer,
    StockUbicacionSerializer,
    TransferirUbicacionInputSerializer,
    TransferirUbicacionResponseSerializer,
    UbicacionAlmacenSerializer,
)
from .services import (
    AutorizacionUbicacionError,
    UbicacionOperacionError,
    reservar_ubicacion,
    transferir_entre_ubicaciones,
)


def _empresas(request):
    return get_empresas_visible(request.user)


class AlmacenViewSet(NulSafeFilterMixin, BaseModelViewSet):
    queryset = Almacen.objects.all()
    serializer_class = AlmacenSerializer
    search_fields = ["nombre_almacen", "codigo_almacen", "direccion"]
    ordering_fields = ["nombre_almacen", "codigo_almacen", "usa_ubicaciones", "activo", "fecha_creacion"]

    def get_queryset(self):
        # R-CODE-1
        return Almacen.objects.filter(id_empresa__in=_empresas(self.request))


class UbicacionAlmacenViewSet(NulSafeFilterMixin, BaseModelViewSet):
    queryset = UbicacionAlmacen.objects.all()
    serializer_class = UbicacionAlmacenSerializer
    search_fields = ["codigo_ubicacion", "nombre_ubicacion", "tipo_ubicacion", "pasillo"]
    ordering_fields = ["codigo_ubicacion", "nombre_ubicacion", "tipo_ubicacion", "activo", "fecha_creacion"]

    def get_queryset(self):
        # R-CODE-1
        qs = UbicacionAlmacen.objects.filter(id_empresa__in=_empresas(self.request))
        almacen_id = self.request.query_params.get("id_almacen") or self.request.query_params.get("almacen")
        if almacen_id:
            qs = qs.filter(id_almacen_id=validar_uuid_param(almacen_id, "almacen"))
        return qs


class StockUbicacionViewSet(NulSafeFilterMixin, EmpresaInjectMixin, BaseModelViewSet):
    queryset = StockUbicacion.objects.all()
    serializer_class = StockUbicacionSerializer
    http_method_names = ["get", "post", "head", "options"]
    search_fields = [
        "id_producto__nombre_producto",
        "id_producto__sku",
        "id_ubicacion__codigo_ubicacion",
        "id_ubicacion__nombre_ubicacion",
        "id_almacen__nombre_almacen",
    ]
    ordering_fields = ["cantidad_disponible", "cantidad_reservada", "fecha_creacion", "fecha_actualizacion"]

    def get_queryset(self):
        # R-CODE-1
        qs = StockUbicacion.objects.filter(id_empresa__in=_empresas(self.request)).select_related(
            "id_almacen", "id_ubicacion", "id_producto", "id_variante"
        )
        almacen_id = self.request.query_params.get("almacen")
        ubicacion_id = self.request.query_params.get("ubicacion")
        producto_id = self.request.query_params.get("producto")
        if almacen_id:
            qs = qs.filter(id_almacen_id=validar_uuid_param(almacen_id, "almacen"))
        if ubicacion_id:
            qs = qs.filter(id_ubicacion_id=validar_uuid_param(ubicacion_id, "ubicacion"))
        if producto_id:
            qs = qs.filter(id_producto_id=validar_uuid_param(producto_id, "producto"))
        return qs.order_by(
            "id_almacen__nombre_almacen", "id_ubicacion__codigo_ubicacion", "id_producto__nombre_producto"
        )

    def _resolver_entidades(self, request, datos):
        empresas = _empresas(request)
        almacen = Almacen.objects.filter(pk=datos["id_almacen"], id_empresa__in=empresas).first()
        if almacen is None:
            return None, Response({"detail": "Almacén no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        producto = Producto.objects.filter(pk=datos["id_producto"], id_empresa__in=empresas).first()
        if producto is None:
            return None, Response({"detail": "Producto no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        variante = None
        if datos.get("id_variante"):
            variante = VarianteProducto.objects.filter(
                pk=datos["id_variante"], id_producto__id_empresa__in=empresas
            ).first()
            if variante is None:
                return None, Response({"detail": "Variante no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        return (empresas, almacen, producto, variante), None

    @swagger_auto_schema(
        request_body=TransferirUbicacionInputSerializer,
        responses={200: TransferirUbicacionResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="transferir")
    def transferir(self, request):
        """POST /api/almacenes/stock-ubicaciones/transferir/ — Traslada stock entre ubicaciones del mismo almacén."""
        ser = TransferirUbicacionInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        datos = ser.validated_data

        resuelto, err = self._resolver_entidades(request, datos)
        if err is not None:
            return err
        empresas, almacen, producto, variante = resuelto

        orig_ub = UbicacionAlmacen.objects.filter(pk=datos["id_ubicacion_origen"], id_empresa__in=empresas).first()
        dest_ub = UbicacionAlmacen.objects.filter(pk=datos["id_ubicacion_destino"], id_empresa__in=empresas).first()
        if orig_ub is None or dest_ub is None:
            return Response({"detail": "Ubicación origen o destino no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        try:
            orig, dest, mov = transferir_entre_ubicaciones(
                empresa=almacen.id_empresa,
                almacen=almacen,
                ubicacion_origen=orig_ub,
                ubicacion_destino=dest_ub,
                producto=producto,
                variante=variante,
                cantidad=datos["cantidad"],
                usuario=request.user,
                autorizado_por=None,
                observaciones=datos.get("observaciones", ""),
            )
        except AutorizacionUbicacionError as exc:
            return domain_error_response(exc, status_code=status.HTTP_403_FORBIDDEN, key="detail")
        except UbicacionOperacionError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        return Response(
            {
                "origen": StockUbicacionSerializer(orig).data,
                "destino": StockUbicacionSerializer(dest).data,
                "id_movimiento": str(mov.pk),
                "tipo_movimiento": mov.tipo_movimiento,
            },
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        request_body=ReservarUbicacionInputSerializer,
        responses={200: StockUbicacionSerializer},
    )
    @action(detail=False, methods=["post"], url_path="reservar")
    def reservar(self, request):
        """POST /api/almacenes/stock-ubicaciones/reservar/ — Reserva o libera stock en una ubicación."""
        ser = ReservarUbicacionInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        datos = ser.validated_data

        resuelto, err = self._resolver_entidades(request, datos)
        if err is not None:
            return err
        empresas, almacen, producto, variante = resuelto

        ubicacion = UbicacionAlmacen.objects.filter(pk=datos["id_ubicacion"], id_empresa__in=empresas).first()
        if ubicacion is None:
            return Response({"detail": "Ubicación no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        try:
            stock = reservar_ubicacion(
                empresa=almacen.id_empresa,
                almacen=almacen,
                ubicacion=ubicacion,
                producto=producto,
                variante=variante,
                cantidad=datos["cantidad"],
                liberar=datos.get("liberar", False),
            )
        except UbicacionOperacionError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        return Response(StockUbicacionSerializer(stock).data, status=status.HTTP_200_OK)
