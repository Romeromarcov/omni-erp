from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoriaProductoViewSet,
    ConversionUnidadMedidaViewSet,
    EntregaViewSet,
    LoteProductoViewSet,
    MovimientoInventarioViewSet,
    PasoOperacionViewSet,
    ProductoViewSet,
    RecepcionViewSet,
    ReglaReabastecimientoViewSet,
    ReportesInventarioViewSet,
    StockActualViewSet,
    StockConsignacionClienteViewSet,
    StockConsignacionProveedorViewSet,
    UnidadMedidaViewSet,
    VarianteProductoViewSet,
)
from .views_supply_chain import ConteoInventarioViewSet

router = DefaultRouter()
router.register(r"unidades-medida", UnidadMedidaViewSet)
router.register(r"categorias-producto", CategoriaProductoViewSet)
router.register(r"productos", ProductoViewSet)
router.register(r"variantes-producto", VarianteProductoViewSet)
router.register(r"stock-actual", StockActualViewSet)
router.register(r"movimientos-inventario", MovimientoInventarioViewSet)
router.register(r"conversiones-unidad-medida", ConversionUnidadMedidaViewSet)
router.register(r"stock-consignacion-cliente", StockConsignacionClienteViewSet)
router.register(r"stock-consignacion-proveedor", StockConsignacionProveedorViewSet)
router.register(r"pasos-operacion", PasoOperacionViewSet)
router.register(r"recepciones", RecepcionViewSet, basename="recepcion")
router.register(r"entregas", EntregaViewSet, basename="entrega")
router.register(r"reportes", ReportesInventarioViewSet, basename="reportes-inventario")
router.register(r"reglas-reabastecimiento", ReglaReabastecimientoViewSet)
router.register(r"lotes-producto", LoteProductoViewSet)
router.register(r"conteos-inventario", ConteoInventarioViewSet, basename="conteo-inventario")

urlpatterns = [
    path("", include(router.urls)),
]
