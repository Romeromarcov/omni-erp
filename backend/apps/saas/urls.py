from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PlanViewSet, SuscripcionViewSet

router = DefaultRouter()
router.register(r"planes", PlanViewSet)
router.register(r"suscripciones", SuscripcionViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
