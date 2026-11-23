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
from .views_parafiscales import PagoContribucionParafiscalViewSet
from .views_seniat import (
    CalcularIGTFITFView,
    ComprobanteRetencionISLRViewSet,
    ComprobanteRetencionIVAViewSet,
    ConceptoRetencionISLRViewSet,
    DocumentoImprentaDigitalViewSet,
    LibroInventarioArt177View,
)

router = DefaultRouter()
router.register(r"configuracion-fiscal", ConfiguracionFiscalEmpresaViewSet)
router.register(r"tasas-iva", TasaIVAEmpresaViewSet)
router.register(r"pagos-parafiscales", PagoContribucionParafiscalViewSet)
router.register(r"conceptos-islr", ConceptoRetencionISLRViewSet)
router.register(r"retenciones-iva", ComprobanteRetencionIVAViewSet)
router.register(r"retenciones-islr", ComprobanteRetencionISLRViewSet)
router.register(r"imprenta-digital", DocumentoImprentaDigitalViewSet)

urlpatterns = [
    path("", include(router.urls)),
    # Libros SENIAT — TXT
    path("libro-ventas/", LibroVentasView.as_view(), name="libro-ventas"),
    path("libro-compras/", LibroComprasView.as_view(), name="libro-compras"),
    # Libros SENIAT — PDF
    path("libro-ventas-pdf/", LibroVentasPDFView.as_view(), name="libro-ventas-pdf"),
    path("libro-compras-pdf/", LibroComprasPDFView.as_view(), name="libro-compras-pdf"),
    # Libro de Inventario Art. 177 LISLR y calculadora IGTF/ITF
    path("libro-inventario-art177/", LibroInventarioArt177View.as_view(), name="libro-inventario-art177"),
    path("calcular-igtf-itf/", CalcularIGTFITFView.as_view(), name="calcular-igtf-itf"),
    # Períodos fiscales
    path("periodos-fiscales/", PeriodoFiscalView.as_view(), name="periodos-fiscales"),
    path(
        "periodos-fiscales/<int:año>/<int:mes>/cerrar/",
        CerrarPeriodoFiscalView.as_view(),
        name="cerrar-periodo-fiscal",
    ),
]
