"""
Tests para StorageService y las acciones de subida/descarga de documentos.

Estrategia:
- StorageService en modo USE_S3=False → no necesita boto3 real.
- StorageService en modo USE_S3=True → mockea el cliente boto3.
- Las acciones de DocumentoViewSet se testean con APIClient y mocks de S3.
"""

import uuid
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from django.contrib.auth import get_user_model

from apps.core.storage import StorageService

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def storage_local(settings):
    """StorageService en modo local (sin S3 real)."""
    settings.USE_S3 = False
    settings.S3_BUCKET_NAME = "omni-erp-test"
    settings.S3_PRESIGNED_URL_EXPIRES = 3600
    return StorageService()


@pytest.fixture
def storage_s3(settings):
    """StorageService en modo S3 (con boto3 mockeado)."""
    settings.USE_S3 = True
    settings.S3_BUCKET_NAME = "omni-erp-test"
    settings.S3_PRESIGNED_URL_EXPIRES = 3600
    settings.S3_ENDPOINT_URL = "http://localhost:9000"
    settings.S3_ACCESS_KEY = "minioadmin"
    settings.S3_SECRET_KEY = "minioadmin123"
    settings.S3_REGION = "us-east-1"
    return StorageService()


@pytest.fixture
def mock_s3_client():
    """Mock del cliente boto3 S3."""
    client = MagicMock()
    client.head_bucket.return_value = {}
    client.put_object.return_value = {"ETag": '"abc123"'}
    client.delete_object.return_value = {}
    client.head_object.return_value = {
        "ContentType": "application/pdf",
        "ContentLength": 1024,
        "LastModified": None,
    }
    client.generate_presigned_url.return_value = (
        "http://localhost:9000/omni-erp-test/empresas/xxx/facturas/file.pdf?sig=abc"
    )
    return client


@pytest.fixture
def sample_file():
    """Archivo PDF de ejemplo para tests de subida."""
    content = b"%PDF-1.4 fake pdf content for testing"
    f = BytesIO(content)
    f.name = "factura-test.pdf"
    return f


# ── Tests StorageService modo LOCAL ──────────────────────────────────────────


class TestStorageServiceLocal:
    """Tests en modo USE_S3=False — sin conexión de red."""

    def test_upload_retorna_key_y_size(self, storage_local, sample_file):
        """upload_file en modo local retorna s3_key con prefijo de empresa y size."""
        empresa_id = str(uuid.uuid4())
        s3_key, size = storage_local.upload_file(
            empresa_id=empresa_id,
            carpeta="facturas",
            filename="factura-test.pdf",
            file_obj=sample_file,
        )
        assert f"empresas/{empresa_id}/facturas/" in s3_key
        assert s3_key.endswith(".pdf")
        assert size > 0

    def test_upload_key_es_unico_en_cada_llamada(self, storage_local):
        """Cada subida genera una key única (UUID en el nombre)."""
        empresa_id = str(uuid.uuid4())
        content = b"%PDF-1.4 file content"  # M-SEC-8: cabecera PDF válida
        f1, f2 = BytesIO(content), BytesIO(content)
        key1, _ = storage_local.upload_file(empresa_id, "docs", "file.pdf", f1)
        key2, _ = storage_local.upload_file(empresa_id, "docs", "file.pdf", f2)
        assert key1 != key2

    def test_upload_bloquea_extension_exe(self, storage_local):
        """Archivos .exe deben ser rechazados con ValueError."""
        with pytest.raises(ValueError, match="no está permitido"):
            storage_local.upload_file(
                empresa_id=str(uuid.uuid4()),
                carpeta="docs",
                filename="malware.exe",
                file_obj=BytesIO(b"MZ bad file"),
            )

    def test_upload_bloquea_extension_sh(self, storage_local):
        """Archivos .sh deben ser rechazados."""
        with pytest.raises(ValueError, match="no está permitido"):
            storage_local.upload_file(
                empresa_id=str(uuid.uuid4()),
                carpeta="docs",
                filename="script.sh",
                file_obj=BytesIO(b"#!/bin/bash"),
            )

    def test_upload_bloquea_archivo_muy_grande(self, storage_local):
        """Archivo mayor a 100 MB debe ser rechazado."""
        big_content = b"x" * (101 * 1024 * 1024)  # 101 MB
        with pytest.raises(ValueError, match="supera el límite"):
            storage_local.upload_file(
                empresa_id=str(uuid.uuid4()),
                carpeta="docs",
                filename="huge.zip",
                file_obj=BytesIO(big_content),
            )

    def test_presigned_url_modo_local_retorna_stub(self, storage_local):
        """En modo local, generate_presigned_url retorna una URL /media/stub/..."""
        url = storage_local.generate_presigned_url("empresas/123/facturas/file.pdf")
        assert url.startswith("/media/stub/")

    def test_delete_modo_local_retorna_true(self, storage_local):
        """delete_file en modo local retorna True sin error."""
        result = storage_local.delete_file("empresas/123/facturas/file.pdf")
        assert result is True

    def test_file_exists_modo_local_retorna_true(self, storage_local):
        """file_exists en modo local siempre retorna True."""
        assert storage_local.file_exists("cualquier/key.pdf") is True

    def test_sanitize_filename_elimina_espacios(self, storage_local):
        """El sanitizador reemplaza espacios y caracteres especiales por _."""
        safe = storage_local._sanitize_filename("mi factura (final).pdf")
        assert " " not in safe
        assert "(" not in safe
        assert safe.endswith(".pdf")

    def test_key_estructura_correcta(self, storage_local, sample_file):
        """La key debe tener la estructura empresas/{id}/{carpeta}/{uuid}_{filename}."""
        empresa_id = "emp-uuid-123"
        key, _ = storage_local.upload_file(empresa_id, "contratos", "contrato.pdf", sample_file)
        parts = key.split("/")
        assert parts[0] == "empresas"
        assert parts[1] == empresa_id
        assert parts[2] == "contratos"
        # El filename en parts[3] debe contener 'contrato.pdf'
        assert "contrato.pdf" in parts[3]


# ── Tests StorageService modo S3 (boto3 mockeado) ───────────────────────────


class TestStorageServiceS3:
    """Tests en modo USE_S3=True con cliente boto3 mockeado."""

    def test_upload_llama_put_object(self, storage_s3, mock_s3_client, sample_file):
        """upload_file debe llamar a put_object exactamente una vez."""
        with patch("apps.core.storage._get_s3_client", return_value=mock_s3_client):
            s3_key, size = storage_s3.upload_file(
                empresa_id="emp-001",
                carpeta="facturas",
                filename="factura.pdf",
                file_obj=sample_file,
            )
        mock_s3_client.put_object.assert_called_once()
        call_kwargs = mock_s3_client.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "omni-erp-test"
        assert "empresas/emp-001/facturas/" in call_kwargs["Key"]

    def test_presigned_url_llama_generate(self, storage_s3, mock_s3_client):
        """generate_presigned_url debe llamar al método boto3 correspondiente."""
        with patch("apps.core.storage._get_s3_client", return_value=mock_s3_client):
            url = storage_s3.generate_presigned_url("empresas/x/facturas/file.pdf")
        mock_s3_client.generate_presigned_url.assert_called_once()
        assert "http" in url

    def test_presigned_url_incluye_filename_hint(self, storage_s3, mock_s3_client):
        """Cuando se pasa filename_hint, se añade ResponseContentDisposition."""
        with patch("apps.core.storage._get_s3_client", return_value=mock_s3_client):
            storage_s3.generate_presigned_url(
                "empresas/x/facturas/file.pdf",
                filename_hint="Factura 001.pdf",
            )
        call_params = mock_s3_client.generate_presigned_url.call_args.kwargs["Params"]
        assert "ResponseContentDisposition" in call_params
        assert "Factura 001.pdf" in call_params["ResponseContentDisposition"]

    def test_delete_llama_delete_object(self, storage_s3, mock_s3_client):
        """delete_file debe llamar a delete_object con el bucket y key correctos."""
        s3_key = "empresas/emp-001/facturas/file.pdf"
        with patch("apps.core.storage._get_s3_client", return_value=mock_s3_client):
            result = storage_s3.delete_file(s3_key)
        mock_s3_client.delete_object.assert_called_once_with(Bucket="omni-erp-test", Key=s3_key)
        assert result is True

    def test_file_exists_true_cuando_head_ok(self, storage_s3, mock_s3_client):
        """file_exists retorna True cuando head_object no lanza excepción."""
        with patch("apps.core.storage._get_s3_client", return_value=mock_s3_client):
            assert storage_s3.file_exists("empresas/emp-001/file.pdf") is True

    def test_file_exists_false_cuando_head_falla(self, storage_s3, mock_s3_client):
        """file_exists retorna False cuando head_object lanza ClientError."""
        mock_s3_client.head_object.side_effect = Exception("404 Not Found")
        with patch("apps.core.storage._get_s3_client", return_value=mock_s3_client):
            assert storage_s3.file_exists("empresas/emp-001/missing.pdf") is False

    def test_get_file_metadata(self, storage_s3, mock_s3_client):
        """get_file_metadata retorna content_type, size y last_modified."""
        with patch("apps.core.storage._get_s3_client", return_value=mock_s3_client):
            meta = storage_s3.get_file_metadata("empresas/emp-001/file.pdf")
        assert meta["content_type"] == "application/pdf"
        assert meta["size"] == 1024


# ── Tests tarea Celery eliminar_archivo_s3 ───────────────────────────────────


class TestEliminarArchivoS3Task:
    """Tests de la tarea Celery gestion_documental.eliminar_archivo_s3."""

    @pytest.fixture(autouse=True)
    def celery_eager(self, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        settings.CELERY_TASK_EAGER_PROPAGATES = True

    def test_tarea_modo_local_retorna_deleted(self, settings):
        """En modo local (USE_S3=False) la tarea termina exitosamente."""
        settings.USE_S3 = False
        from apps.gestion_documental.tasks import eliminar_archivo_s3

        result = eliminar_archivo_s3.apply(
            kwargs={
                "s3_key": "empresas/emp-001/facturas/file.pdf",
                "documento_id": str(uuid.uuid4()),
            }
        )
        assert result.successful()
        assert result.get()["status"] == "deleted"

    def test_tarea_s3_llama_delete(self, settings, mock_s3_client):
        """En modo S3, la tarea llama a delete_file en el storage."""
        settings.USE_S3 = True
        settings.S3_BUCKET_NAME = "omni-erp-test"
        settings.S3_ENDPOINT_URL = "http://localhost:9000"
        settings.S3_ACCESS_KEY = "minioadmin"
        settings.S3_SECRET_KEY = "minioadmin123"
        settings.S3_REGION = "us-east-1"
        settings.S3_PRESIGNED_URL_EXPIRES = 3600

        from apps.gestion_documental.tasks import eliminar_archivo_s3

        with patch("apps.core.storage._get_s3_client", return_value=mock_s3_client):
            result = eliminar_archivo_s3.apply(
                kwargs={
                    "s3_key": "empresas/emp-001/facturas/file.pdf",
                }
            )
        assert result.successful()
        mock_s3_client.delete_object.assert_called_once()


# ── Tests acciones de DocumentoViewSet ──────────────────────────────────────


class TestDocumentoViewSetAcciones:
    """Tests de las acciones subir / descargar / eliminar-archivo."""

    @pytest.fixture
    def api_client_auth(self, user_a):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=user_a)
        return client

    def test_subir_sin_archivo_retorna_400(self, db, api_client_auth, empresa_a):
        """POST /api/gestion-documental/documentos/subir/ sin archivo → 400."""
        response = api_client_auth.post(
            "/api/gestion-documental/documentos/subir/",
            data={"empresa_id": str(empresa_a.pk)},
        )
        assert response.status_code == 400
        assert "archivo" in response.data["error"]

    def test_subir_sin_empresa_retorna_400(self, db, api_client_auth):
        """POST /api/gestion-documental/documentos/subir/ sin empresa_id → 400."""
        pdf = BytesIO(b"%PDF test")
        pdf.name = "test.pdf"
        response = api_client_auth.post(
            "/api/gestion-documental/documentos/subir/",
            data={"archivo": pdf},
            format="multipart",
        )
        assert response.status_code == 400
        assert "empresa_id" in response.data["error"]

    def test_subir_empresa_ajena_retorna_403(self, db, api_client_auth, empresa_b):
        """POST con empresa_id de otra empresa → 403."""
        pdf = BytesIO(b"%PDF test")
        pdf.name = "test.pdf"
        response = api_client_auth.post(
            "/api/gestion-documental/documentos/subir/",
            data={"archivo": pdf, "empresa_id": str(empresa_b.pk)},
            format="multipart",
        )
        assert response.status_code == 403

    def test_subir_crea_documento_en_db(self, db, settings, api_client_auth, empresa_a):
        """POST exitoso → documento creado en DB, retorna 201."""
        settings.USE_S3 = False
        from apps.gestion_documental.models import Documento

        pdf = BytesIO(b"%PDF-1.4 fake pdf for test")
        pdf.name = "contrato.pdf"

        response = api_client_auth.post(
            "/api/gestion-documental/documentos/subir/",
            data={"archivo": pdf, "empresa_id": str(empresa_a.pk)},
            format="multipart",
        )

        assert response.status_code == 201
        assert Documento.objects.filter(id_empresa=empresa_a).count() == 1
        doc = Documento.objects.get(id_empresa=empresa_a)
        assert doc.nombre_archivo == "contrato.pdf"
        assert "empresas/" in doc.ruta_almacenamiento

    def test_descargar_genera_url(self, db, settings, api_client_auth, empresa_a, user_a):
        """GET /api/gestion-documental/documentos/{pk}/descargar/ → 200 + url."""
        settings.USE_S3 = False
        from apps.gestion_documental.models import Documento

        # Crear documento de prueba
        doc = Documento.objects.create(
            id_empresa=empresa_a,
            nombre_archivo="reporte.pdf",
            tipo_contenido="application/pdf",
            tamano_bytes=1024,
            ruta_almacenamiento=f"empresas/{empresa_a.pk}/docs/abc123_reporte.pdf",
            id_usuario_subida=user_a,
        )

        response = api_client_auth.get(f"/api/gestion-documental/documentos/{doc.pk}/descargar/")
        assert response.status_code == 200
        assert "url" in response.data
        assert "expires_in" in response.data
        assert response.data["nombre_archivo"] == "reporte.pdf"

    def test_descargar_documento_ajeno_retorna_404(self, db, settings, api_client_auth, empresa_b, user_b):
        """GET descargar de un documento de otra empresa → 404."""
        settings.USE_S3 = False
        from apps.gestion_documental.models import Documento

        doc = Documento.objects.create(
            id_empresa=empresa_b,
            nombre_archivo="privado.pdf",
            tipo_contenido="application/pdf",
            tamano_bytes=512,
            ruta_almacenamiento="empresas/emp-b/docs/privado.pdf",
            id_usuario_subida=user_b,
        )

        response = api_client_auth.get(f"/api/gestion-documental/documentos/{doc.pk}/descargar/")
        assert response.status_code == 404

    def test_eliminar_borra_de_db(self, db, settings, api_client_auth, empresa_a, user_a):
        """DELETE eliminar-archivo borra el registro de DB."""
        settings.USE_S3 = False
        settings.CELERY_TASK_ALWAYS_EAGER = True
        settings.CELERY_TASK_EAGER_PROPAGATES = True

        from apps.gestion_documental.models import Documento

        doc = Documento.objects.create(
            id_empresa=empresa_a,
            nombre_archivo="temp.pdf",
            tipo_contenido="application/pdf",
            tamano_bytes=256,
            ruta_almacenamiento="empresas/emp-a/docs/temp.pdf",
            id_usuario_subida=user_a,
        )
        doc_id = str(doc.pk)

        response = api_client_auth.delete(f"/api/gestion-documental/documentos/{doc.pk}/eliminar-archivo/")
        assert response.status_code == 200
        assert not Documento.objects.filter(pk=doc_id).exists()
