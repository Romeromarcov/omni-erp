from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConfiguracionFiscalEmpresaViewSet, TasaIVAEmpresaViewSet
from .views_libros import LibroComprasView, LibroVentasView

router = DefaultRouter()
router.register(r"configuracion-fiscal", ConfiguracionFiscalEmpresaViewSet)
router.register(r"tasas-iva", TasaIVAEmpresaViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path("libro-ventas/", LibroVentasView.as_view(), name="libro-ventas"),
    path("libro-compras/", LibroComprasView.as_view(), name="libro-compras"),
]
