from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.core.storage import StorageService
from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import Carpeta, Documento, PermisoDocumento, VinculoDocumento
from .serializers import (
    CarpetaSerializer,
    DocumentoSerializer,
    PermisoDocumentoSerializer,
    VinculoDocumentoSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


class CarpetaViewSet(BaseModelViewSet):
    queryset = Carpeta.objects.all()
    serializer_class = CarpetaSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar por empresas visibles
        return Carpeta.objects.filter(id_empresa__in=_empresas(self.request)).order_by("nombre_carpeta")

    def perform_create(self, serializer):
        # El creador lo fija el servidor (no el cliente): coherente con
        # `id_usuario_subida` de los documentos y con R-CODE-1.
        serializer.save(id_usuario_creacion=self.request.user)


class DocumentoViewSet(BaseModelViewSet):
    queryset = Documento.objects.all()
    serializer_class = DocumentoSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        # R-CODE-1: filtrar por empresas visibles. M-BUG-4: excluir soft-deleted.
        return (
            Documento.objects.filter(id_empresa__in=_empresas(self.request), activo=True)
            .order_by("-fecha_subida")
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="subir",
        parser_classes=[MultiPartParser, FormParser],
    )
    def subir(self, request):
        """
        Sube un archivo a S3/MinIO y crea el registro Documento en DB.

        Parámetros multipart:
            archivo         — Archivo binario (requerido)
            empresa_id      — UUID de la empresa (requerido)
            carpeta_id      — UUID de la carpeta destino (opcional)
            descripcion     — Texto libre (opcional)
            carpeta_nombre  — Subcarpeta lógica en S3 (default 'general')

        Retorna:
            201 + DocumentoSerializer si la subida fue exitosa.
            400 si faltan campos requeridos o el archivo es inválido.
        """
        archivo = request.FILES.get("archivo")
        if not archivo:
            return Response(
                {"error": 'El campo "archivo" es requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        empresa_id = request.data.get("empresa_id")
        if not empresa_id:
            return Response(
                {"error": 'El campo "empresa_id" es requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verificar que la empresa pertenece al usuario
        empresas_ids = list(_empresas(request).values_list("pk", flat=True))
        if str(empresa_id) not in [str(e) for e in empresas_ids]:
            return Response(
                {"error": "No tienes acceso a esta empresa."},
                status=status.HTTP_403_FORBIDDEN,
            )

        carpeta_s3 = request.data.get("carpeta_nombre", "general")
        carpeta_id = request.data.get("carpeta_id")
        descripcion = request.data.get("descripcion", "")

        storage = StorageService()

        try:
            s3_key, size_bytes = storage.upload_file(
                empresa_id=empresa_id,
                carpeta=carpeta_s3,
                filename=archivo.name,
                file_obj=archivo,
                content_type=archivo.content_type,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Obtener empresa y usuario para el registro
        from apps.core.models import Empresa

        empresa = Empresa.objects.get(pk=empresa_id)

        documento = Documento.objects.create(
            id_empresa=empresa,
            nombre_archivo=archivo.name,
            tipo_contenido=archivo.content_type or "application/octet-stream",
            tamano_bytes=size_bytes,
            ruta_almacenamiento=s3_key,
            id_usuario_subida=request.user,
            id_carpeta_id=carpeta_id if carpeta_id else None,
            descripcion=descripcion,
        )

        serializer = self.get_serializer(documento)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="descargar")
    def descargar(self, request, pk=None):
        """
        Genera una URL pre-firmada para descarga temporal del documento.

        Retorna:
            200 + {'url': '...', 'expires_in': 3600}
            404 si el documento no existe o no pertenece a la empresa del usuario.
        """
        documento = self.get_object()  # aplica get_queryset → R-CODE-1

        storage = StorageService()
        url = storage.generate_presigned_url(
            s3_key=documento.ruta_almacenamiento,
            filename_hint=documento.nombre_archivo,
        )

        return Response(
            {
                "url": url,
                "expires_in": storage.presigned_expires,
                "nombre_archivo": documento.nombre_archivo,
            }
        )

    @action(detail=True, methods=["delete"], url_path="eliminar-archivo")
    def eliminar_archivo(self, request, pk=None):
        """
        Elimina el archivo de S3 y el registro Documento de la DB.

        La eliminación del objeto S3 se delega a una tarea Celery para
        no bloquear la request en caso de lentitud del storage.
        """
        documento = self.get_object()  # aplica get_queryset → R-CODE-1

        # M-BUG-4: borrado lógico. NO se borra el registro ni el archivo en S3
        # (recuperable); solo se marca activo=False y deja de listarse. Evita
        # perder historial/auditoría de documentos (incluidos fiscales).
        documento_id = str(documento.pk)
        nombre_archivo = documento.nombre_archivo
        documento.activo = False
        documento.save(update_fields=["activo"])

        return Response(
            {
                "mensaje": f'Documento "{nombre_archivo}" eliminado correctamente.',
                "documento_id": documento_id,
            },
            status=status.HTTP_200_OK,
        )


class VinculoDocumentoViewSet(BaseModelViewSet):
    queryset = VinculoDocumento.objects.all()
    serializer_class = VinculoDocumentoSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar vía FK id_documento → id_empresa
        return VinculoDocumento.objects.filter(id_documento__id_empresa__in=_empresas(self.request))


class PermisoDocumentoViewSet(BaseModelViewSet):
    queryset = PermisoDocumento.objects.all()
    serializer_class = PermisoDocumentoSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar vía FK id_documento → id_empresa
        return PermisoDocumento.objects.filter(id_documento__id_empresa__in=_empresas(self.request))
