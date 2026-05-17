from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CuentaPorPagarViewSet
from .views_abono import AbonoCxPViewSet

router = DefaultRouter()
router.register(r"cuentas-por-pagar", CuentaPorPagarViewSet)
router.register(r"abonos-cxp", AbonoCxPViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
