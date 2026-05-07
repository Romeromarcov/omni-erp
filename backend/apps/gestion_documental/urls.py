from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CarpetaViewSet, DocumentoViewSet, VinculoDocumentoViewSet,
    PermisoDocumentoViewSet
)

router = DefaultRouter()
router.register(r'carpetas', CarpetaViewSet)
router.register(r'documentos', DocumentoViewSet)
router.register(r'vinculos-documento', VinculoDocumentoViewSet)
router.register(r'permisos-documento', PermisoDocumentoViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
