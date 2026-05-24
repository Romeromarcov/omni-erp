from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PrediccionAgenteViewSet

router = DefaultRouter()
router.register(r"predicciones", PrediccionAgenteViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
