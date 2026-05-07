from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CostoProduccionViewSet, CostoEstandarProductoViewSet,
    AnalisisVariacionCostoViewSet
)

router = DefaultRouter()
router.register(r'costos-produccion', CostoProduccionViewSet)
router.register(r'costos-estandar-producto', CostoEstandarProductoViewSet)
router.register(r'analisis-variacion-costo', AnalisisVariacionCostoViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
