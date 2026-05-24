from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DetalleFacturaCompraViewSet,
    DetalleOfertaProveedorViewSet,
    DetalleOrdenCompraViewSet,
    DetalleRecepcionMercanciaViewSet,
    DetalleRequisicionCompraViewSet,
    DetalleSolicitudCotizacionViewSet,
    FacturaCompraViewSet,
    OfertaProveedorViewSet,
    OrdenCompraViewSet,
    RecepcionMercanciaViewSet,
    RequisicionCompraViewSet,
    SolicitudCotizacionViewSet,
)

router = DefaultRouter()
router.register(r"ordenes-compra", OrdenCompraViewSet)
router.register(r"detalles-orden-compra", DetalleOrdenCompraViewSet)
router.register(r"recepciones-mercancia", RecepcionMercanciaViewSet)
router.register(r"facturas-compra", FacturaCompraViewSet)
router.register(r"requisiciones-compra", RequisicionCompraViewSet)
router.register(r"detalles-requisicion-compra", DetalleRequisicionCompraViewSet)
router.register(r"solicitudes-cotizacion", SolicitudCotizacionViewSet)
router.register(r"detalles-solicitud-cotizacion", DetalleSolicitudCotizacionViewSet)
router.register(r"ofertas-proveedor", OfertaProveedorViewSet)
router.register(r"detalles-oferta-proveedor", DetalleOfertaProveedorViewSet)
router.register(r"detalles-recepcion-mercancia", DetalleRecepcionMercanciaViewSet)
router.register(r"detalles-factura-compra", DetalleFacturaCompraViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
