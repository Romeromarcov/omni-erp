from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CajaViewSet, MovimientoInternoFondoViewSet, OperacionCambioDivisaViewSet

router = DefaultRouter()
router.register(r'cajas', CajaViewSet)
router.register(r'movimientos-internos-fondo', MovimientoInternoFondoViewSet)
router.register(r'operaciones-cambio-divisa', OperacionCambioDivisaViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
