from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ConfiguracionIntegracionViewSet, LogIntegracionViewSet, MapeoCampoViewSet
)

router = DefaultRouter()
router.register(r'configuracion-integracion', ConfiguracionIntegracionViewSet)
router.register(r'logs-integracion', LogIntegracionViewSet)
router.register(r'mapeo-campos', MapeoCampoViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
