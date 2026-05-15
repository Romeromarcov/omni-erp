from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AsientoContableViewSet, DetalleAsientoViewSet, PlanCuentasViewSet

router = DefaultRouter()
router.register(r"plan-cuentas", PlanCuentasViewSet)
router.register(r"asientos-contables", AsientoContableViewSet)
router.register(r"detalles-asiento", DetalleAsientoViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
