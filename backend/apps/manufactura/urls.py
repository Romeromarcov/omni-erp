from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ListaMaterialesViewSet, RutaProduccionViewSet, OrdenProduccionViewSet,
    ConsumoMaterialViewSet, ProduccionTerminadaViewSet,
    ListaMaterialesDetalleViewSet, CentroTrabajoViewSet,
    OperacionProduccionViewSet, RutaProduccionDetalleViewSet,
    RegistroOperacionViewSet
)

router = DefaultRouter()
router.register(r'listas-materiales', ListaMaterialesViewSet)
router.register(r'rutas-produccion', RutaProduccionViewSet)
router.register(r'ordenes-produccion', OrdenProduccionViewSet)
router.register(r'consumos-material', ConsumoMaterialViewSet)
router.register(r'produccion-terminada', ProduccionTerminadaViewSet)
router.register(r'listas-materiales-detalle', ListaMaterialesDetalleViewSet)
router.register(r'centros-trabajo', CentroTrabajoViewSet)
router.register(r'operaciones-produccion', OperacionProduccionViewSet)
router.register(r'rutas-produccion-detalle', RutaProduccionDetalleViewSet)
router.register(r'registros-operacion', RegistroOperacionViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
