from rest_framework import serializers
from .models import Carpeta, Documento, VinculoDocumento, PermisoDocumento

class CarpetaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carpeta
        fields = '__all__'

class DocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Documento
        fields = '__all__'

class VinculoDocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VinculoDocumento
        fields = '__all__'

class PermisoDocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermisoDocumento
        fields = '__all__'
