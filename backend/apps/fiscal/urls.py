from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConfiguracionFiscalEmpresaViewSet, TasaIVAEmpresaViewSet

router = DefaultRouter()
router.register(r"configuracion-fiscal", ConfiguracionFiscalEmpresaViewSet)
router.register(r"tasas-iva", TasaIVAEmpresaViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
