from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LogAuditoriaViewSet

router = DefaultRouter()
router.register(r"logs-auditoria", LogAuditoriaViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
