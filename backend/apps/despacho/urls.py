from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DespachoViewSet, DetalleDespachoViewSet
from .views_tms import (
    ConductorViewSet,
    ParadaEntregaViewSet,
    RutaDespachoViewSet,
    TarifaFleteViewSet,
    TrackingPublicoParadaView,
    VehiculoViewSet,
    ZonaLogisticaViewSet,
)

router = DefaultRouter()
router.register(r"despachos", DespachoViewSet)
router.register(r"detalles-despacho", DetalleDespachoViewSet)
router.register(r"zonas-logisticas", ZonaLogisticaViewSet, basename="zona-logistica")
router.register(r"tarifas-flete", TarifaFleteViewSet, basename="tarifa-flete")
router.register(r"vehiculos", VehiculoViewSet, basename="vehiculo")
router.register(r"conductores", ConductorViewSet, basename="conductor")
router.register(r"rutas", RutaDespachoViewSet, basename="ruta-despacho")
router.register(r"paradas", ParadaEntregaViewSet, basename="parada-entrega")

urlpatterns = [
    path("tracking/<uuid:token>/", TrackingPublicoParadaView.as_view(), name="tracking-publico-parada"),
    path("", include(router.urls)),
]
