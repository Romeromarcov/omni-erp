from rest_framework import viewsets
from .models import Carpeta, Documento, VinculoDocumento, PermisoDocumento
from .serializers import CarpetaSerializer, DocumentoSerializer, VinculoDocumentoSerializer, PermisoDocumentoSerializer
from apps.core.viewsets import BaseModelViewSet

class CarpetaViewSet(BaseModelViewSet):
    queryset = Carpeta.objects.all()
    serializer_class = CarpetaSerializer

class DocumentoViewSet(BaseModelViewSet):
    queryset = Documento.objects.all()
    serializer_class = DocumentoSerializer

class VinculoDocumentoViewSet(BaseModelViewSet):
    queryset = VinculoDocumento.objects.all()
    serializer_class = VinculoDocumentoSerializer

class PermisoDocumentoViewSet(BaseModelViewSet):
    queryset = PermisoDocumento.objects.all()
    serializer_class = PermisoDocumentoSerializer
