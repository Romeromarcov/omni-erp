from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .portal_cliente import (
    PortalClientePagosView,
    PortalClientePedidosView,
    PortalClienteResumenView,
    PortalClienteTrackingView,
    SolicitarOTPPortalView,
    VerificarOTPPortalView,
)
from .portal_vendedor import PortalVendedorViewSet
from .views import (
    ComisionVentaViewSet,
    CotizacionViewSet,
    DetalleCotizacionViewSet,
    DetalleDevolucionVentaViewSet,
    DetalleFacturaFiscalViewSet,
    DetalleNotaCreditoFiscalViewSet,
    DetalleNotaCreditoVentaViewSet,
    DetalleNotaDebitoFiscalViewSet,
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
    NotaDebitoFiscalViewSet,
    NotaVentaViewSet,
    PedidoViewSet,
    ReglaPrecioDinamicoViewSet,
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
router.register(r"notas-debito-fiscales", NotaDebitoFiscalViewSet)
router.register(r"detalles-nota-debito-fiscal", DetalleNotaDebitoFiscalViewSet)
router.register(r"listas-precio", ListaPrecioViewSet)
router.register(r"detalles-precio", DetallePrecioViewSet)
router.register(r"reglas-precio-dinamico", ReglaPrecioDinamicoViewSet)
router.register(r"esquemas-comision", EsquemaComisionViewSet)
router.register(r"esquemas-comision-categorias", EsquemaComisionCategoriaViewSet)
router.register(r"comisiones", ComisionVentaViewSet)
router.register(r"portal-vendedor", PortalVendedorViewSet, basename="portal-vendedor")

urlpatterns = [
    path("portal-cliente/auth/solicitar-otp/", SolicitarOTPPortalView.as_view(), name="portal-cliente-solicitar-otp"),
    path("portal-cliente/auth/verificar-otp/", VerificarOTPPortalView.as_view(), name="portal-cliente-verificar-otp"),
    path("portal-cliente/resumen/", PortalClienteResumenView.as_view(), name="portal-cliente-resumen"),
    path("portal-cliente/pagos/", PortalClientePagosView.as_view(), name="portal-cliente-pagos"),
    path("portal-cliente/pedidos/", PortalClientePedidosView.as_view(), name="portal-cliente-pedidos"),
    path("portal-cliente/tracking/", PortalClienteTrackingView.as_view(), name="portal-cliente-tracking"),
    path("", include(router.urls)),
]
