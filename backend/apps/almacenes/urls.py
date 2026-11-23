from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AlmacenViewSet, StockUbicacionViewSet, UbicacionAlmacenViewSet
from .views_transito import TransferenciaTransitoViewSet

router = DefaultRouter()
router.register(r"almacenes", AlmacenViewSet)
router.register(r"ubicaciones-almacen", UbicacionAlmacenViewSet)
router.register(r"stock-ubicaciones", StockUbicacionViewSet)
router.register(r"transferencias-transito", TransferenciaTransitoViewSet, basename="transferencia-transito")

urlpatterns = [
    path("", include(router.urls)),
]
