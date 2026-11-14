from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BotUsuarioViewSet, IngestaBotViewSet

router = DefaultRouter()
router.register("ingest", IngestaBotViewSet, basename="bots-ingest")
router.register("usuarios", BotUsuarioViewSet, basename="bots-usuarios")

urlpatterns = [path("", include(router.urls))]
