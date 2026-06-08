from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PlanViewSet, SignupView, SuscripcionViewSet

router = DefaultRouter()
router.register(r"planes", PlanViewSet)
router.register(r"suscripciones", SuscripcionViewSet)

urlpatterns = [
    path("signup/", SignupView.as_view(), name="saas-signup"),
    path("", include(router.urls)),
]
