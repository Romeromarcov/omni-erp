from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TipoAprobacionViewSet, FlujoAprobacionViewSet,
    SolicitudAprobacionViewSet, RegistroAprobacionViewSet
)

router = DefaultRouter()
router.register(r'tipos-aprobacion', TipoAprobacionViewSet)
router.register(r'flujos-aprobacion', FlujoAprobacionViewSet)
router.register(r'solicitudes-aprobacion', SolicitudAprobacionViewSet)
router.register(r'registros-aprobacion', RegistroAprobacionViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
