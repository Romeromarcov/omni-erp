from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CuentaPorPagarViewSet

router = DefaultRouter()
router.register(r'cuentas-por-pagar', CuentaPorPagarViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
