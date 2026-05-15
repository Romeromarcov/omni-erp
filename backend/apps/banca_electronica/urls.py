from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CuentaBancariaEmpresaViewSet

router = DefaultRouter()
router.register(r"cuentas-bancarias-empresa", CuentaBancariaEmpresaViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
