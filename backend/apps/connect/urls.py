"""URLs autenticadas de Omni Connect (``/api/connect/``)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConnectAnaliticasView, PerfilViewSet, TarjetaViewSet

router = DefaultRouter()
router.register(r"perfiles", PerfilViewSet, basename="connect-perfil")
router.register(r"tarjetas", TarjetaViewSet, basename="connect-tarjeta")

urlpatterns = [
    path("analiticas/", ConnectAnaliticasView.as_view(), name="connect-analiticas"),
    path("", include(router.urls)),
]
