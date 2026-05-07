from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PlantillaMigracionViewSet, ProcesoMigracionViewSet,
    DetalleErrorMigracionViewSet
)

router = DefaultRouter()
router.register(r'plantillas-migracion', PlantillaMigracionViewSet)
router.register(r'procesos-migracion', ProcesoMigracionViewSet)
router.register(r'detalles-error-migracion', DetalleErrorMigracionViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
