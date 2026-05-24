from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AnalisisVariacionCostoViewSet, CostoEstandarProductoViewSet, CostoProduccionViewSet

router = DefaultRouter()
router.register(r"costos-produccion", CostoProduccionViewSet)
router.register(r"costos-estandar-producto", CostoEstandarProductoViewSet)
router.register(r"analisis-variacion-costo", AnalisisVariacionCostoViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
