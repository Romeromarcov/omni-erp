from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BotBitacoraView,
    BotControlViewSet,
    BotDestinosView,
    BotHeartbeatView,
    BotUsuarioViewSet,
    IngestaBotViewSet,
)

router = DefaultRouter()
router.register("ingest", IngestaBotViewSet, basename="bots-ingest")
router.register("usuarios", BotUsuarioViewSet, basename="bots-usuarios")
router.register("control", BotControlViewSet, basename="bots-control")

urlpatterns = [
    path("heartbeat/", BotHeartbeatView.as_view(), name="bots-heartbeat"),
    path("destinos/", BotDestinosView.as_view(), name="bots-destinos"),
    path("bitacora/", BotBitacoraView.as_view(), name="bots-bitacora"),
    path("", include(router.urls)),
]
