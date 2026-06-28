from rest_framework import serializers

from .models import Carpeta, Documento, PermisoDocumento, VinculoDocumento


class CarpetaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carpeta
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_carpeta",
            "nombre_carpeta",
            "fecha_creacion",
            "es_publica",
            "activo",
            "id_empresa",
            "id_carpeta_padre",
            "id_usuario_creacion",
        ]
        # El creador lo fija el servidor desde request.user (CarpetaViewSet
        # .perform_create); el cliente nunca debe poder suplantarlo (R-CODE-1).
        read_only_fields = ["id_usuario_creacion"]


class DocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Documento
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_documento",
            "nombre_archivo",
            "tipo_contenido",
            "tamano_bytes",
            "ruta_almacenamiento",
            "fecha_subida",
            "descripcion",
            "activo",
            "version",
            "id_empresa",
            "id_usuario_subida",
            "id_carpeta",
        ]


class VinculoDocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VinculoDocumento
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_vinculo",
            "id_entidad_origen",
            "nombre_modelo_origen",
            "tipo_vinculo",
            "fecha_vinculo",
            "id_documento",
        ]


class PermisoDocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermisoDocumento
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_permiso_documento",
            "puede_ver",
            "puede_editar",
            "puede_eliminar",
            "fecha_asignacion",
            "id_documento",
            "id_usuario",
            "id_rol",
        ]
