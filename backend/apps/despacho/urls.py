from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DespachoViewSet, DetalleDespachoViewSet

router = DefaultRouter()
router.register(r"despachos", DespachoViewSet)
router.register(r"detalles-despacho", DetalleDespachoViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
