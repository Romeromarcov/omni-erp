from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CuentaPorCobrarViewSet
from .views_abono import AbonoCxCViewSet

router = DefaultRouter()
router.register(r"cuentas-por-cobrar", CuentaPorCobrarViewSet)
router.register(r"abonos-cxc", AbonoCxCViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
