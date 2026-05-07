from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProveedorViewSet, ContactoProveedorViewSet, CuentaBancariaProveedorViewSet

router = DefaultRouter()
router.register(r'proveedores', ProveedorViewSet)
router.register(r'contactos-proveedor', ContactoProveedorViewSet)
router.register(r'cuentas-bancarias-proveedor', CuentaBancariaProveedorViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
