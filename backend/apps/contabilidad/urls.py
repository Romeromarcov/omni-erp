from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AsientoContableViewSet,
    CentroCostoViewSet,
    DetalleAsientoViewSet,
    DiarioContableViewSet,
    MapeoContableViewSet,
    PeriodoContableViewSet,
    PlanCuentasViewSet,
)
from .views_reportes import (
    ReporteBalanceComprobacionView,
    ReporteBalanceGeneralView,
    ReporteEstadoResultadosView,
    ReporteLibroMayorAuxiliarView,
)

router = DefaultRouter()
router.register(r"plan-cuentas", PlanCuentasViewSet)
router.register(r"diarios", DiarioContableViewSet)
router.register(r"centros-costo", CentroCostoViewSet)
router.register(r"periodos-contables", PeriodoContableViewSet)
router.register(r"asientos-contables", AsientoContableViewSet)
router.register(r"detalles-asiento", DetalleAsientoViewSet)
router.register(r"mapeos-contables", MapeoContableViewSet)

urlpatterns = [
    path(
        "reportes/balance-comprobacion/",
        ReporteBalanceComprobacionView.as_view(),
        name="reporte-balance-comprobacion",
    ),
    path(
        "reportes/estado-resultados/",
        ReporteEstadoResultadosView.as_view(),
        name="reporte-estado-resultados",
    ),
    path(
        "reportes/balance-general/",
        ReporteBalanceGeneralView.as_view(),
        name="reporte-balance-general",
    ),
    path(
        "reportes/libro-mayor-auxiliar/",
        ReporteLibroMayorAuxiliarView.as_view(),
        name="reporte-libro-mayor-auxiliar",
    ),
    path("", include(router.urls)),
]
