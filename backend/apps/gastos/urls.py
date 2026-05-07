from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoriaGastoViewSet, GastoViewSet, ReembolsoGastoViewSet

router = DefaultRouter()
router.register(r'categorias-gasto', CategoriaGastoViewSet)
router.register(r'gastos', GastoViewSet)
router.register(r'reembolsos-gasto', ReembolsoGastoViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
