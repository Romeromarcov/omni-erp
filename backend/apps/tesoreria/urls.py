from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CajaViewSet,
    ConciliacionBancariaViewSet,
    ConfiguracionConciliacionCuentaViewSet,
    ExtractoBancarioArchivoViewSet,
    MovimientoBancarioViewSet,
    MovimientoInternoFondoViewSet,
    OperacionCambioDivisaViewSet,
    PropuestaConciliacionBancariaViewSet,
)

router = DefaultRouter()
router.register(r"cajas", CajaViewSet)
router.register(r"movimientos-internos-fondo", MovimientoInternoFondoViewSet)
router.register(r"operaciones-cambio-divisa", OperacionCambioDivisaViewSet)
router.register(r"extractos-bancarios", ExtractoBancarioArchivoViewSet, basename="extracto-bancario")
router.register(r"movimientos-bancarios", MovimientoBancarioViewSet)
router.register(r"conciliaciones-bancarias", ConciliacionBancariaViewSet)
router.register(
    r"configuraciones-conciliacion",
    ConfiguracionConciliacionCuentaViewSet,
    basename="configuracion-conciliacion",
)
router.register(
    r"propuestas-conciliacion",
    PropuestaConciliacionBancariaViewSet,
    basename="propuesta-conciliacion",
)

urlpatterns = [
    path("", include(router.urls)),
]
