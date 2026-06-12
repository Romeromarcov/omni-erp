"""
Backfill de cobertura — apps/gestion_documental/tasks.py (plan "Cero Dudas").

Cero llamadas de red: ``StorageService`` y el cliente boto3 se mockean.
Cubre:
- ``eliminar_archivo_s3``: éxito y reintento con backoff (Retry).
- ``limpiar_archivos_huerfanos``: USE_S3=False (no-op), huérfano eliminado,
  archivo reciente respetado (ventana 24h), archivo con registro en DB
  conservado y error de borrado tolerado.
"""
from datetime import datetime, timedelta, timezone as tz
from unittest import mock

import pytest

from celery.exceptions import Retry

from django.test import override_settings

from apps.gestion_documental.tasks import eliminar_archivo_s3, limpiar_archivos_huerfanos

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── eliminar_archivo_s3 ───────────────────────────────────────────────────────


class TestEliminarArchivoS3:
    def test_eliminacion_exitosa(self):
        storage = mock.Mock()
        with mock.patch("apps.core.storage.StorageService", return_value=storage):
            res = eliminar_archivo_s3("empresas/e1/doc.pdf", documento_id="d1")

        storage.delete_file.assert_called_once_with("empresas/e1/doc.pdf")
        assert res["s3_key"] == "empresas/e1/doc.pdf"
        assert res["status"] == "deleted"

    def test_fallo_dispara_retry_con_backoff(self):
        """En invocación directa (called_directly=True) ``self.retry`` re-lanza la
        excepción original en lugar de ``Retry``; en un worker real sería ``Retry``.
        En ambos casos el fallo NO se traga: la tarea se reintenta/propaga.
        """
        storage = mock.Mock()
        storage.delete_file.side_effect = ConnectionError("S3 caído")
        with mock.patch("apps.core.storage.StorageService", return_value=storage):
            with pytest.raises((Retry, ConnectionError)):
                eliminar_archivo_s3("empresas/e1/doc.pdf")
        storage.delete_file.assert_called_once_with("empresas/e1/doc.pdf")


# ── limpiar_archivos_huerfanos ────────────────────────────────────────────────


def _pagina(objetos):
    """Simula una página del paginator list_objects_v2."""
    return {"Contents": objetos}


class TestLimpiarArchivosHuerfanos:
    def test_use_s3_false_es_noop(self, empresa_a):
        # settings de test no activan USE_S3
        res = limpiar_archivos_huerfanos(str(empresa_a.id_empresa))
        assert res == {"analizado": 0, "eliminado": 0}

    @override_settings(USE_S3=True, S3_BUCKET_NAME="bucket-test")
    def test_elimina_solo_huerfanos_viejos(self, empresa_a, user_a):
        from apps.gestion_documental.models import Documento

        prefijo = f"empresas/{empresa_a.id_empresa}/"
        key_registrado = f"{prefijo}registrado.pdf"
        key_huerfano = f"{prefijo}huerfano.pdf"
        key_reciente = f"{prefijo}reciente.pdf"
        key_error = f"{prefijo}con-error.pdf"

        Documento.objects.create(
            id_empresa=empresa_a,
            nombre_archivo="registrado.pdf",
            tipo_contenido="application/pdf",
            tamano_bytes=10,
            ruta_almacenamiento=key_registrado,
            id_usuario_subida=user_a,
        )

        viejo = datetime.now(tz=tz.utc) - timedelta(days=3)
        reciente = datetime.now(tz=tz.utc) - timedelta(hours=1)

        client = mock.Mock()
        client.get_paginator.return_value.paginate.return_value = [
            _pagina([
                {"Key": key_registrado, "LastModified": viejo},
                {"Key": key_huerfano, "LastModified": viejo},
                {"Key": key_reciente, "LastModified": reciente},  # ventana 24h
                {"Key": key_error, "LastModified": viejo},
            ]),
        ]

        def _delete(Bucket, Key):
            if Key == key_error:
                raise RuntimeError("AccessDenied")

        client.delete_object.side_effect = _delete

        with mock.patch("apps.core.storage._get_s3_client", return_value=client):
            res = limpiar_archivos_huerfanos(str(empresa_a.id_empresa))

        assert res["analizado"] == 4
        # huerfano eliminado OK; con-error intentado pero falló (tolerado)
        assert res["eliminado"] == 1
        claves_borradas = [c.kwargs["Key"] for c in client.delete_object.call_args_list]
        assert key_huerfano in claves_borradas
        assert key_error in claves_borradas  # se intentó
        assert key_registrado not in claves_borradas  # tiene registro en DB
        assert key_reciente not in claves_borradas  # dentro de la ventana de seguridad
        # Pagina con el prefijo de la empresa y el bucket configurado
        client.get_paginator.assert_called_once_with("list_objects_v2")
        client.get_paginator.return_value.paginate.assert_called_once_with(
            Bucket="bucket-test", Prefix=prefijo
        )

    @override_settings(USE_S3=True, S3_BUCKET_NAME="bucket-test")
    def test_pagina_sin_contents(self, empresa_a):
        client = mock.Mock()
        client.get_paginator.return_value.paginate.return_value = [{}]
        with mock.patch("apps.core.storage._get_s3_client", return_value=client):
            res = limpiar_archivos_huerfanos(str(empresa_a.id_empresa))
        assert res["analizado"] == 0
        assert res["eliminado"] == 0
        client.delete_object.assert_not_called()
