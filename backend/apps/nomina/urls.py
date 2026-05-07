from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PeriodoNominaViewSet, ConceptoNominaViewSet, ProcesoNominaViewSet,
    NominaViewSet, DetalleNominaViewSet, ProcesoNominaExtrasalarialViewSet,
    NominaExtrasalarialViewSet
)

router = DefaultRouter()
router.register(r'periodos-nomina', PeriodoNominaViewSet)
router.register(r'conceptos-nomina', ConceptoNominaViewSet)
router.register(r'procesos-nomina', ProcesoNominaViewSet)
router.register(r'nominas', NominaViewSet)
router.register(r'detalles-nomina', DetalleNominaViewSet)
router.register(r'procesos-nomina-extrasalarial', ProcesoNominaExtrasalarialViewSet)
router.register(r'nominas-extrasalarial', NominaExtrasalarialViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
