from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api.chat import AsistenteChatView
from .views import EjecucionAgenteViewSet, PrediccionAgenteViewSet

router = DefaultRouter()
router.register(r"predicciones", PrediccionAgenteViewSet)
router.register(r"ejecuciones", EjecucionAgenteViewSet, basename="ejecucion-agente")

urlpatterns = [
    path("chat/", AsistenteChatView.as_view(), name="asistente-chat"),
    path("", include(router.urls)),
]
