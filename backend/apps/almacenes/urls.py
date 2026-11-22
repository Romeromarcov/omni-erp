from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AlmacenViewSet, StockUbicacionViewSet, UbicacionAlmacenViewSet

router = DefaultRouter()
router.register(r"almacenes", AlmacenViewSet)
router.register(r"ubicaciones-almacen", UbicacionAlmacenViewSet)
router.register(r"stock-ubicaciones", StockUbicacionViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
