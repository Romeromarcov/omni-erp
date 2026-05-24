from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConfiguracionFiscalEmpresaViewSet, TasaIVAEmpresaViewSet
from .views_libros import (
    CerrarPeriodoFiscalView,
    LibroComprasPDFView,
    LibroComprasView,
    LibroVentasPDFView,
    LibroVentasView,
    PeriodoFiscalView,
)

router = DefaultRouter()
router.register(r"configuracion-fiscal", ConfiguracionFiscalEmpresaViewSet)
router.register(r"tasas-iva", TasaIVAEmpresaViewSet)

urlpatterns = [
    path("", include(router.urls)),
    # Libros SENIAT — TXT
    path("libro-ventas/", LibroVentasView.as_view(), name="libro-ventas"),
    path("libro-compras/", LibroComprasView.as_view(), name="libro-compras"),
    # Libros SENIAT — PDF
    path("libro-ventas-pdf/", LibroVentasPDFView.as_view(), name="libro-ventas-pdf"),
    path("libro-compras-pdf/", LibroComprasPDFView.as_view(), name="libro-compras-pdf"),
    # Períodos fiscales
    path("periodos-fiscales/", PeriodoFiscalView.as_view(), name="periodos-fiscales"),
    path(
        "periodos-fiscales/<int:año>/<int:mes>/cerrar/",
        CerrarPeriodoFiscalView.as_view(),
        name="cerrar-periodo-fiscal",
    ),
]
