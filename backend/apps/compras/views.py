
from rest_framework import viewsets
from .models import (
    OrdenCompra, DetalleOrdenCompra, RecepcionMercancia, FacturaCompra,
    RequisicionCompra, DetalleRequisicionCompra, SolicitudCotizacion,
    DetalleSolicitudCotizacion, OfertaProveedor, DetalleOfertaProveedor,
    DetalleRecepcionMercancia, DetalleFacturaCompra
)
from .serializers import (
    OrdenCompraSerializer, DetalleOrdenCompraSerializer,
    RecepcionMercanciaSerializer, FacturaCompraSerializer,
    RequisicionCompraSerializer, DetalleRequisicionCompraSerializer,
    SolicitudCotizacionSerializer, DetalleSolicitudCotizacionSerializer,
    OfertaProveedorSerializer, DetalleOfertaProveedorSerializer,
    DetalleRecepcionMercanciaSerializer, DetalleFacturaCompraSerializer
)
from apps.core.viewsets import BaseModelViewSet

class OrdenCompraViewSet(BaseModelViewSet):
    queryset = OrdenCompra.objects.all()
    serializer_class = OrdenCompraSerializer

class DetalleOrdenCompraViewSet(BaseModelViewSet):
    queryset = DetalleOrdenCompra.objects.all()
    serializer_class = DetalleOrdenCompraSerializer

class RecepcionMercanciaViewSet(BaseModelViewSet):
    queryset = RecepcionMercancia.objects.all()
    serializer_class = RecepcionMercanciaSerializer

class FacturaCompraViewSet(BaseModelViewSet):
    queryset = FacturaCompra.objects.all()
    serializer_class = FacturaCompraSerializer


class RequisicionCompraViewSet(BaseModelViewSet):
    queryset = RequisicionCompra.objects.all()
    serializer_class = RequisicionCompraSerializer


class DetalleRequisicionCompraViewSet(BaseModelViewSet):
    queryset = DetalleRequisicionCompra.objects.all()
    serializer_class = DetalleRequisicionCompraSerializer


class SolicitudCotizacionViewSet(BaseModelViewSet):
    queryset = SolicitudCotizacion.objects.all()
    serializer_class = SolicitudCotizacionSerializer


class DetalleSolicitudCotizacionViewSet(BaseModelViewSet):
    queryset = DetalleSolicitudCotizacion.objects.all()
    serializer_class = DetalleSolicitudCotizacionSerializer


class OfertaProveedorViewSet(BaseModelViewSet):
    queryset = OfertaProveedor.objects.all()
    serializer_class = OfertaProveedorSerializer


class DetalleOfertaProveedorViewSet(BaseModelViewSet):
    queryset = DetalleOfertaProveedor.objects.all()
    serializer_class = DetalleOfertaProveedorSerializer


class DetalleRecepcionMercanciaViewSet(BaseModelViewSet):
    queryset = DetalleRecepcionMercancia.objects.all()
    serializer_class = DetalleRecepcionMercanciaSerializer


class DetalleFacturaCompraViewSet(BaseModelViewSet):
    queryset = DetalleFacturaCompra.objects.all()
    serializer_class = DetalleFacturaCompraSerializer
