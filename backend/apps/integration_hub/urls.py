from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ConectorInstanciaViewSet,
    ConectorProveedorViewSet,
    IntegrationHubStatusView,
    JobSincronizacionViewSet,
)

router = DefaultRouter()
router.register(r"proveedores", ConectorProveedorViewSet, basename="conector-proveedor")
router.register(r"instancias", ConectorInstanciaViewSet, basename="conector-instancia")
router.register(r"jobs", JobSincronizacionViewSet, basename="job-sincronizacion")

urlpatterns = [
    path("", include(router.urls)),
    path("status/", IntegrationHubStatusView.as_view(), name="integration-hub-status"),
]
