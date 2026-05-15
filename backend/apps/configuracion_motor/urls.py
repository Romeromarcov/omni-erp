from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CatalogoValorViewSet, ParametroSistemaViewSet, TipoDocumentoViewSet

router = DefaultRouter()
router.register(r"tipos-documento", TipoDocumentoViewSet)
router.register(r"parametros-sistema", ParametroSistemaViewSet)
router.register(r"catalogos-valor", CatalogoValorViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
