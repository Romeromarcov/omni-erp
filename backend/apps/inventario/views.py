from decimal import Decimal

from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import (
    CategoriaProducto,
    ConversionUnidadMedida,
    MovimientoInventario,
    Producto,
    StockActual,
    StockConsignacionCliente,
    StockConsignacionProveedor,
    UnidadMedida,
    VarianteProducto,
)
from .serializers import (
    CategoriaProductoSerializer,
    ConversionUnidadMedidaSerializer,
    MovimientoInventarioSerializer,
    ProductoSerializer,
    StockActualSerializer,
    StockConsignacionClienteSerializer,
    StockConsignacionProveedorSerializer,
    UnidadMedidaSerializer,
    VarianteProductoSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


# ── Catálogo ──────────────────────────────────────────────────────────────────


class UnidadMedidaViewSet(BaseModelViewSet):
    queryset = UnidadMedida.objects.all()
    serializer_class = UnidadMedidaSerializer

    def get_queryset(self):
        return UnidadMedida.objects.filter(id_empresa__in=_empresas(self.request))


class CategoriaProductoViewSet(BaseModelViewSet):
    queryset = CategoriaProducto.objects.all()
    serializer_class = CategoriaProductoSerializer

    def get_queryset(self):
        return CategoriaProducto.objects.filter(id_empresa__in=_empresas(self.request)).order_by(
            "nombre_categoria"
        )


class ProductoViewSet(BaseModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer

    def get_queryset(self):
        qs = Producto.objects.filter(id_empresa__in=_empresas(self.request)).select_related(
            "id_categoria", "id_unidad_medida_base"
        )
        empresa_id = self.request.query_params.get("empresa")
        if empresa_id:
            qs = qs.filter(id_empresa=empresa_id)
        return qs

    @action(detail=True, methods=["get"], url_path="kardex")
    def kardex(self, request, pk=None):
        """
        GET /api/inventario/productos/{pk}/kardex/

        Query params:
          almacen      — UUID de almacén (requerido para saldo corriente)
          fecha_desde  — YYYY-MM-DD (inclusive)
          fecha_hasta  — YYYY-MM-DD (inclusive)
        """
        from .services import delta_para_almacen

        producto = self.get_object()
        almacen_id = request.query_params.get("almacen")
        fecha_desde = request.query_params.get("fecha_desde")
        fecha_hasta = request.query_params.get("fecha_hasta")

        qs = (
            MovimientoInventario.objects.filter(
                id_empresa__in=_empresas(request),
                id_producto=producto,
            )
            .select_related("id_almacen_origen", "id_almacen_destino", "id_usuario_registro")
        )

        if almacen_id:
            qs = qs.filter(Q(id_almacen_origen=almacen_id) | Q(id_almacen_destino=almacen_id))

        if fecha_desde:
            qs = qs.filter(fecha_hora_movimiento__date__gte=fecha_desde)

        if fecha_hasta:
            qs = qs.filter(fecha_hora_movimiento__date__lte=fecha_hasta)

        qs = qs.order_by("fecha_hora_movimiento", "fecha_creacion")

        # Calcular saldo inicial si hay filtro de fecha y almacén
        saldo = Decimal("0")
        if almacen_id and fecha_desde:
            prior_qs = (
                MovimientoInventario.objects.filter(
                    id_empresa__in=_empresas(request),
                    id_producto=producto,
                    fecha_hora_movimiento__date__lt=fecha_desde,
                )
                .filter(Q(id_almacen_origen=almacen_id) | Q(id_almacen_destino=almacen_id))
            )
            for mov in prior_qs:
                saldo += delta_para_almacen(mov, almacen_id)

        kardex_items = []
        for mov in qs:
            saldo_anterior = saldo
            delta = delta_para_almacen(mov, almacen_id) if almacen_id else Decimal("0")
            saldo += delta

            kardex_items.append(
                {
                    "id_movimiento": str(mov.id_movimiento_inventario),
                    "fecha_hora": mov.fecha_hora_movimiento,
                    "tipo_movimiento": mov.tipo_movimiento,
                    "cantidad": str(mov.cantidad),
                    "delta": str(delta),
                    "almacen_origen": (
                        mov.id_almacen_origen.nombre_almacen if mov.id_almacen_origen else None
                    ),
                    "almacen_destino": (
                        mov.id_almacen_destino.nombre_almacen if mov.id_almacen_destino else None
                    ),
                    "costo_unitario": (
                        str(mov.costo_unitario_movimiento)
                        if mov.costo_unitario_movimiento is not None
                        else None
                    ),
                    "saldo_anterior": str(saldo_anterior),
                    "saldo_posterior": str(saldo),
                    "observaciones": mov.observaciones,
                }
            )

        return Response(
            {
                "producto_id": str(producto.id_producto),
                "producto_nombre": producto.nombre_producto,
                "almacen_id": almacen_id,
                "saldo_final": str(saldo),
                "kardex": kardex_items,
            }
        )


class VarianteProductoViewSet(BaseModelViewSet):
    queryset = VarianteProducto.objects.all()
    serializer_class = VarianteProductoSerializer


# ── Stock ─────────────────────────────────────────────────────────────────────


class StockActualViewSet(BaseModelViewSet):
    queryset = StockActual.objects.all()
    serializer_class = StockActualSerializer

    def get_queryset(self):
        qs = StockActual.objects.filter(id_empresa__in=_empresas(self.request)).select_related(
            "id_producto", "id_almacen"
        )
        producto_id = self.request.query_params.get("producto")
        almacen_id = self.request.query_params.get("almacen")
        empresa_id = self.request.query_params.get("empresa")
        if producto_id:
            qs = qs.filter(id_producto=producto_id)
        if almacen_id:
            qs = qs.filter(id_almacen=almacen_id)
        if empresa_id:
            qs = qs.filter(id_empresa=empresa_id)
        return qs.order_by("id_producto", "id_almacen")


# ── Movimientos ───────────────────────────────────────────────────────────────


class MovimientoInventarioViewSet(BaseModelViewSet):
    queryset = MovimientoInventario.objects.all()
    serializer_class = MovimientoInventarioSerializer

    def get_queryset(self):
        return (
            MovimientoInventario.objects.filter(id_empresa__in=_empresas(self.request))
            .select_related("id_producto", "id_almacen_origen", "id_almacen_destino")
            .order_by("-fecha_hora_movimiento")
        )

    def perform_create(self, serializer):
        from .services import MovimientoInvalidoError, StockInsuficienteError, registrar_movimiento

        vd = serializer.validated_data
        try:
            movimiento = registrar_movimiento(
                empresa=vd["id_empresa"],
                fecha_hora_movimiento=vd["fecha_hora_movimiento"],
                tipo_movimiento=vd["tipo_movimiento"],
                producto=vd["id_producto"],
                variante=vd.get("id_variante"),
                cantidad=vd["cantidad"],
                almacen_origen=vd.get("id_almacen_origen"),
                almacen_destino=vd.get("id_almacen_destino"),
                costo_unitario=vd.get("costo_unitario_movimiento"),
                documento_origen_id=vd.get("id_documento_origen"),
                nombre_modelo_origen=vd.get("nombre_modelo_origen"),
                usuario=self.request.user,
                observaciones=vd.get("observaciones"),
            )
        except (StockInsuficienteError, MovimientoInvalidoError) as exc:
            raise ValidationError(str(exc)) from exc

        serializer.instance = movimiento


# ── Otras tablas de inventario ────────────────────────────────────────────────


class ConversionUnidadMedidaViewSet(BaseModelViewSet):
    queryset = ConversionUnidadMedida.objects.all()
    serializer_class = ConversionUnidadMedidaSerializer

    def get_queryset(self):
        return ConversionUnidadMedida.objects.filter(id_empresa__in=_empresas(self.request))


class StockConsignacionClienteViewSet(BaseModelViewSet):
    queryset = StockConsignacionCliente.objects.all()
    serializer_class = StockConsignacionClienteSerializer

    def get_queryset(self):
        return StockConsignacionCliente.objects.filter(id_empresa__in=_empresas(self.request))


class StockConsignacionProveedorViewSet(BaseModelViewSet):
    queryset = StockConsignacionProveedor.objects.all()
    serializer_class = StockConsignacionProveedorSerializer

    def get_queryset(self):
        return StockConsignacionProveedor.objects.filter(id_empresa__in=_empresas(self.request))
