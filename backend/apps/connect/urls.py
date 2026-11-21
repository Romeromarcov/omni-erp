"""URLs autenticadas de Omni Connect (``/api/connect/``)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PerfilViewSet

router = DefaultRouter()
router.register(r"perfiles", PerfilViewSet, basename="connect-perfil")

urlpatterns = [
    path("", include(router.urls)),
]
