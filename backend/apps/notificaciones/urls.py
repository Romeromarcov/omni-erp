from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ChatterDocumentoViewSet, NotificacionViewSet

router = DefaultRouter()
router.register(r"notificaciones", NotificacionViewSet, basename="notificacion")
router.register(r"chatter", ChatterDocumentoViewSet, basename="chatter-documento")

urlpatterns = [
    path("", include(router.urls)),
]
