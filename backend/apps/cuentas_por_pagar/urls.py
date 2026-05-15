from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CuentaPorPagarViewSet

router = DefaultRouter()
router.register(r"cuentas-por-pagar", CuentaPorPagarViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
