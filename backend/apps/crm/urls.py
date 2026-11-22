from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ActividadViewSet,
    ClienteViewSet,
    ContactoClienteViewSet,
    DireccionClienteViewSet,
    EtapaViewSet,
    LeadViewSet,
    PipelineViewSet,
)

router = DefaultRouter()
router.register(r"clientes", ClienteViewSet)
router.register(r"contactos-cliente", ContactoClienteViewSet)
router.register(r"direcciones-cliente", DireccionClienteViewSet)
router.register(r"pipelines", PipelineViewSet)
router.register(r"etapas", EtapaViewSet)
router.register(r"leads", LeadViewSet)
router.register(r"actividades", ActividadViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
