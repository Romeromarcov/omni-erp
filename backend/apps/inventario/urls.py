from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoriaProductoViewSet,
    ConversionUnidadMedidaViewSet,
    MovimientoInventarioViewSet,
    ProductoViewSet,
    StockActualViewSet,
    StockConsignacionClienteViewSet,
    StockConsignacionProveedorViewSet,
    UnidadMedidaViewSet,
    VarianteProductoViewSet,
)

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

urlpatterns = [
    path("", include(router.urls)),
]
