from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TipoDocumentoViewSet, ParametroSistemaViewSet, CatalogoValorViewSet

router = DefaultRouter()
router.register(r'tipos-documento', TipoDocumentoViewSet)
router.register(r'parametros-sistema', ParametroSistemaViewSet)
router.register(r'catalogos-valor', CatalogoValorViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
