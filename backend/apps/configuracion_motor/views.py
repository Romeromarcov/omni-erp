from rest_framework import viewsets
from .models import TipoDocumento, ParametroSistema, CatalogoValor
from .serializers import TipoDocumentoSerializer, ParametroSistemaSerializer, CatalogoValorSerializer

class TipoDocumentoViewSet(viewsets.ModelViewSet):
    queryset = TipoDocumento.objects.all()
    serializer_class = TipoDocumentoSerializer

class ParametroSistemaViewSet(viewsets.ModelViewSet):
    queryset = ParametroSistema.objects.all()
    serializer_class = ParametroSistemaSerializer

class CatalogoValorViewSet(viewsets.ModelViewSet):
    queryset = CatalogoValor.objects.all()
    serializer_class = CatalogoValorSerializer
