from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ComisionVentaViewSet,
    CotizacionViewSet,
    DetalleCotizacionViewSet,
    DetalleDevolucionVentaViewSet,
    DetalleFacturaFiscalViewSet,
    DetalleNotaCreditoFiscalViewSet,
    DetalleNotaCreditoVentaViewSet,
    DetalleNotaVentaViewSet,
    DetallePedidoViewSet,
    DetallePrecioViewSet,
    DevolucionVentaViewSet,
    EsquemaComisionCategoriaViewSet,
    EsquemaComisionViewSet,
    FacturaFiscalViewSet,
    ListaPrecioViewSet,
    NotaCreditoFiscalViewSet,
    NotaCreditoVentaViewSet,
    NotaVentaViewSet,
    PedidoViewSet,
)

router = DefaultRouter()
router.register(r"pedidos", PedidoViewSet)
router.register(r"detalles-pedido", DetallePedidoViewSet)
router.register(r"notas-venta", NotaVentaViewSet)
router.register(r"detalles-nota-venta", DetalleNotaVentaViewSet)
router.register(r"facturas-fiscales", FacturaFiscalViewSet)
router.register(r"detalles-factura-fiscal", DetalleFacturaFiscalViewSet)
router.register(r"notas-credito-venta", NotaCreditoVentaViewSet)
router.register(r"detalles-nota-credito-venta", DetalleNotaCreditoVentaViewSet)
router.register(r"devoluciones-venta", DevolucionVentaViewSet)
router.register(r"detalles-devolucion-venta", DetalleDevolucionVentaViewSet)
router.register(r"cotizaciones", CotizacionViewSet)
router.register(r"detalles-cotizacion", DetalleCotizacionViewSet)
router.register(r"notas-credito-fiscal", NotaCreditoFiscalViewSet)
router.register(r"detalles-nota-credito-fiscal", DetalleNotaCreditoFiscalViewSet)
router.register(r"listas-precio", ListaPrecioViewSet)
router.register(r"detalles-precio", DetallePrecioViewSet)
router.register(r"esquemas-comision", EsquemaComisionViewSet)
router.register(r"esquemas-comision-categorias", EsquemaComisionCategoriaViewSet)
router.register(r"comisiones", ComisionVentaViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
