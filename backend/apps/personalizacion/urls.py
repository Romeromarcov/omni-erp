from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PersonalizacionConfigViewSet

router = DefaultRouter()
router.register(r"configuraciones", PersonalizacionConfigViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
