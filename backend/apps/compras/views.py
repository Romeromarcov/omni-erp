from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import (
    DetalleFacturaCompra,
    DetalleOfertaProveedor,
    DetalleOrdenCompra,
    DetalleRecepcionMercancia,
    DetalleRequisicionCompra,
    DetalleSolicitudCotizacion,
    FacturaCompra,
    OfertaProveedor,
    OrdenCompra,
    RecepcionMercancia,
    RequisicionCompra,
    SolicitudCotizacion,
)
from .serializers import (
    DetalleFacturaCompraSerializer,
    DetalleOfertaProveedorSerializer,
    DetalleOrdenCompraSerializer,
    DetalleRecepcionMercanciaSerializer,
    DetalleRequisicionCompraSerializer,
    DetalleSolicitudCotizacionSerializer,
    FacturaCompraSerializer,
    OfertaProveedorSerializer,
    OrdenCompraSerializer,
    RecepcionMercanciaSerializer,
    RequisicionCompraSerializer,
    SolicitudCotizacionSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


class OrdenCompraViewSet(BaseModelViewSet):
    queryset = OrdenCompra.objects.all()
    serializer_class = OrdenCompraSerializer

    def get_queryset(self):
        # R-CODE-1
        return OrdenCompra.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=True, methods=["post"], url_path="aprobar")
    def aprobar(self, request, pk=None):
        """POST /ordenes-compra/{pk}/aprobar/ — Aprueba una OC en estado BORRADOR/ENVIADA."""
        from .services import CompraError, aprobar_orden_compra
        oc = self.get_object()
        try:
            aprobar_orden_compra(oc, request.user)
        except CompraError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Orden aprobada.", "estado": oc.estado})


class DetalleOrdenCompraViewSet(BaseModelViewSet):
    queryset = DetalleOrdenCompra.objects.all()
    serializer_class = DetalleOrdenCompraSerializer

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleOrdenCompra.objects.filter(id_orden_compra__id_empresa__in=_empresas(self.request))


class RecepcionMercanciaViewSet(BaseModelViewSet):
    queryset = RecepcionMercancia.objects.all()
    serializer_class = RecepcionMercanciaSerializer

    def get_queryset(self):
        # R-CODE-1
        return RecepcionMercancia.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=False, methods=["post"], url_path="recepcionar")
    def recepcionar(self, request):
        """
        POST /recepciones-mercancia/recepcionar/ — Registra una recepción de mercancía.

        Body: {
            "orden_compra_id": "<uuid>",
            "almacen_id": "<uuid>",
            "items": [{"producto_id": "<uuid>", "cantidad": 10, "costo_unitario": "25.00"}, ...]
        }
        """
        from apps.almacenes.models import Almacen
        from .models import OrdenCompra
        from .services import CompraError, registrar_recepcion

        oc_id = request.data.get("orden_compra_id")
        almacen_id = request.data.get("almacen_id")
        items_raw = request.data.get("items", [])

        if not oc_id or not almacen_id or not items_raw:
            return Response(
                {"detail": "orden_compra_id, almacen_id e items son requeridos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            oc = OrdenCompra.objects.get(pk=oc_id, id_empresa__in=_empresas(request))
            # H-SEC-11: el almacén debe ser de una empresa visible del usuario.
            almacen = Almacen.objects.get(pk=almacen_id, id_empresa__in=_empresas(request))
        except (OrdenCompra.DoesNotExist, Almacen.DoesNotExist) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        # Resolve product instances for each item
        from apps.inventario.models import Producto
        items = []
        for it in items_raw:
            try:
                # H-SEC-11: el producto debe ser de una empresa visible del usuario.
                producto = Producto.objects.get(pk=it["producto_id"], id_empresa__in=_empresas(request))
            except (Producto.DoesNotExist, KeyError):
                return Response(
                    {"detail": f"Producto '{it.get('producto_id')}' no encontrado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            items.append({
                "producto": producto,
                "cantidad": it.get("cantidad"),
                "costo_unitario": it.get("costo_unitario", "0"),
            })

        try:
            resultado = registrar_recepcion(oc, almacen, request.user, items)
        except CompraError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "recepcion_id": str(resultado["recepcion"].pk),
                "movimientos": len(resultado["movimientos"]),
                "cxp_id": str(resultado["cxp"].pk) if resultado.get("cxp") else None,
                "monto_total": str(resultado["recepcion"].monto_total),
            },
            status=status.HTTP_201_CREATED,
        )


class FacturaCompraViewSet(BaseModelViewSet):
    queryset = FacturaCompra.objects.all()
    serializer_class = FacturaCompraSerializer

    def get_queryset(self):
        # R-CODE-1
        return FacturaCompra.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=False, methods=["post"], url_path="facturar")
    def facturar(self, request):
        """
        POST /facturas-compra/facturar/ — Registra la factura de proveedor sobre una recepción.

        Body: {"recepcion_id": "<uuid>", "numero_factura": "FAC-001", "fecha_emision": "YYYY-MM-DD"}
        """
        from .models import RecepcionMercancia
        from .services import CompraError, registrar_factura_compra

        recepcion_id = request.data.get("recepcion_id")
        numero_factura = request.data.get("numero_factura")

        if not recepcion_id or not numero_factura:
            return Response(
                {"detail": "recepcion_id y numero_factura son requeridos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            recepcion = RecepcionMercancia.objects.get(
                pk=recepcion_id, id_empresa__in=_empresas(request)
            )
        except RecepcionMercancia.DoesNotExist:
            return Response({"detail": "Recepción no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        try:
            resultado = registrar_factura_compra(
                recepcion,
                numero_factura=numero_factura,
                fecha_emision=request.data.get("fecha_emision"),
            )
        except CompraError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "factura_id": str(resultado["factura"].pk),
                "numero_factura": resultado["factura"].numero_factura,
                "monto_total": str(resultado["factura"].monto_total),
            },
            status=status.HTTP_201_CREATED,
        )


class RequisicionCompraViewSet(BaseModelViewSet):
    queryset = RequisicionCompra.objects.all()
    serializer_class = RequisicionCompraSerializer

    def get_queryset(self):
        # R-CODE-1
        return RequisicionCompra.objects.filter(id_empresa__in=_empresas(self.request))


class DetalleRequisicionCompraViewSet(BaseModelViewSet):
    queryset = DetalleRequisicionCompra.objects.all()
    serializer_class = DetalleRequisicionCompraSerializer

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleRequisicionCompra.objects.filter(id_requisicion__id_empresa__in=_empresas(self.request))


class SolicitudCotizacionViewSet(BaseModelViewSet):
    queryset = SolicitudCotizacion.objects.all()
    serializer_class = SolicitudCotizacionSerializer

    def get_queryset(self):
        # R-CODE-1
        return SolicitudCotizacion.objects.filter(id_empresa__in=_empresas(self.request))


class DetalleSolicitudCotizacionViewSet(BaseModelViewSet):
    queryset = DetalleSolicitudCotizacion.objects.all()
    serializer_class = DetalleSolicitudCotizacionSerializer

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleSolicitudCotizacion.objects.filter(
            id_solicitud_cotizacion__id_empresa__in=_empresas(self.request)
        )


class OfertaProveedorViewSet(BaseModelViewSet):
    queryset = OfertaProveedor.objects.all()
    serializer_class = OfertaProveedorSerializer

    def get_queryset(self):
        # R-CODE-1 via SolicitudCotizacion parent
        return OfertaProveedor.objects.filter(
            id_solicitud_cotizacion__id_empresa__in=_empresas(self.request)
        )


class DetalleOfertaProveedorViewSet(BaseModelViewSet):
    queryset = DetalleOfertaProveedor.objects.all()
    serializer_class = DetalleOfertaProveedorSerializer

    def get_queryset(self):
        # R-CODE-1 via OfertaProveedor → SolicitudCotizacion
        return DetalleOfertaProveedor.objects.filter(
            id_oferta__id_solicitud_cotizacion__id_empresa__in=_empresas(self.request)
        )


class DetalleRecepcionMercanciaViewSet(BaseModelViewSet):
    queryset = DetalleRecepcionMercancia.objects.all()
    serializer_class = DetalleRecepcionMercanciaSerializer

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleRecepcionMercancia.objects.filter(id_recepcion__id_empresa__in=_empresas(self.request))


class DetalleFacturaCompraViewSet(BaseModelViewSet):
    queryset = DetalleFacturaCompra.objects.all()
    serializer_class = DetalleFacturaCompraSerializer

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleFacturaCompra.objects.filter(id_factura_compra__id_empresa__in=_empresas(self.request))
