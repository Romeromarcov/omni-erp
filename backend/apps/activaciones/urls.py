from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CalendarioActivacionViewSet,
    EventoActivacionViewSet,
    RecursoActivacionViewSet,
)

router = DefaultRouter()
router.register(
    "calendarios", CalendarioActivacionViewSet, basename="activ-calendarios"
)
router.register("recursos", RecursoActivacionViewSet, basename="activ-recursos")
router.register("eventos", EventoActivacionViewSet, basename="activ-eventos")

urlpatterns = [path("", include(router.urls))]
