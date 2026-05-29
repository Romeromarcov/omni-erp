from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PrediccionAgenteViewSet
from .api.chat import AsistenteChatView

router = DefaultRouter()
router.register(r"predicciones", PrediccionAgenteViewSet)

urlpatterns = [
    path("chat/", AsistenteChatView.as_view(), name="asistente-chat"),
    path("", include(router.urls)),
]
