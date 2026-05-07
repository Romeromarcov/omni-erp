from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClienteViewSet, ContactoClienteViewSet, DireccionClienteViewSet

router = DefaultRouter()
router.register(r'clientes', ClienteViewSet)
router.register(r'contactos-cliente', ContactoClienteViewSet)
router.register(r'direcciones-cliente', DireccionClienteViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
