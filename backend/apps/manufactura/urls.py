from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CentroTrabajoViewSet,
    ConfiguracionManufacturaViewSet,
    ConsumoMaterialViewSet,
    EtapaProduccionViewSet,
    ListaMaterialesDetalleViewSet,
    ListaMaterialesViewSet,
    OperacionProduccionViewSet,
    OrdenProduccionViewSet,
    ProduccionTerminadaViewSet,
    RegistroOperacionViewSet,
    RutaProduccionDetalleViewSet,
    RutaProduccionViewSet,
)

router = DefaultRouter()
router.register(r"listas-materiales", ListaMaterialesViewSet)
router.register(r"rutas-produccion", RutaProduccionViewSet)
router.register(r"ordenes-produccion", OrdenProduccionViewSet)
router.register(r"consumos-material", ConsumoMaterialViewSet)
router.register(r"produccion-terminada", ProduccionTerminadaViewSet)
router.register(r"listas-materiales-detalle", ListaMaterialesDetalleViewSet)
router.register(r"centros-trabajo", CentroTrabajoViewSet)
router.register(r"operaciones-produccion", OperacionProduccionViewSet)
router.register(r"rutas-produccion-detalle", RutaProduccionDetalleViewSet)
router.register(r"registros-operacion", RegistroOperacionViewSet)
router.register(r"etapas-produccion", EtapaProduccionViewSet)
router.register(r"configuracion", ConfiguracionManufacturaViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
