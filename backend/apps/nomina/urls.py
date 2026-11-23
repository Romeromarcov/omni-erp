from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ConceptoNominaViewSet,
    DetalleNominaViewSet,
    NominaExtrasalarialViewSet,
    NominaViewSet,
    PeriodoNominaViewSet,
    ProcesoNominaExtrasalarialViewSet,
    ProcesoNominaViewSet,
)
from .views_dual import (
    DispersionPagoNominaViewSet,
    FichaSalarialDualViewSet,
    PrestamoEmpleadoViewSet,
    SimuladorLiquidacionLOTTTView,
)

router = DefaultRouter()
router.register(r"periodos-nomina", PeriodoNominaViewSet)
router.register(r"conceptos-nomina", ConceptoNominaViewSet)
router.register(r"procesos-nomina", ProcesoNominaViewSet)
router.register(r"nominas", NominaViewSet)
router.register(r"detalles-nomina", DetalleNominaViewSet)
router.register(r"procesos-nomina-extrasalarial", ProcesoNominaExtrasalarialViewSet)
router.register(r"nominas-extrasalarial", NominaExtrasalarialViewSet)
router.register(r"fichas-salariales-dual", FichaSalarialDualViewSet)
router.register(r"prestamos-empleados", PrestamoEmpleadoViewSet)
router.register(r"dispersiones-nomina", DispersionPagoNominaViewSet)

urlpatterns = [
    path("simulador-liquidacion/", SimuladorLiquidacionLOTTTView.as_view(), name="nomina-simulador-liquidacion"),
    path("", include(router.urls)),
]
