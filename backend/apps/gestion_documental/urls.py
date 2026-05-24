from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CarpetaViewSet, DocumentoViewSet, PermisoDocumentoViewSet, VinculoDocumentoViewSet

router = DefaultRouter()
router.register(r"carpetas", CarpetaViewSet)
router.register(r"documentos", DocumentoViewSet)
router.register(r"vinculos-documento", VinculoDocumentoViewSet)
router.register(r"permisos-documento", PermisoDocumentoViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
