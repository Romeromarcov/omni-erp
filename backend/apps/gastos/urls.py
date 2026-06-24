from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoriaGastoViewSet, DetalleGastoViewSet, GastoViewSet, ReembolsoGastoViewSet

router = DefaultRouter()
router.register(r"categorias-gasto", CategoriaGastoViewSet)
router.register(r"gastos", GastoViewSet)
router.register(r"detalles-gasto", DetalleGastoViewSet)
router.register(r"reembolsos-gasto", ReembolsoGastoViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
