from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ContactoProveedorViewSet, CuentaBancariaProveedorViewSet, ProveedorViewSet

router = DefaultRouter()
router.register(r"proveedores", ProveedorViewSet)
router.register(r"contactos-proveedor", ContactoProveedorViewSet)
router.register(r"cuentas-bancarias-proveedor", CuentaBancariaProveedorViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
