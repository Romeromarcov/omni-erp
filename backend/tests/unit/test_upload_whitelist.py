"""H-SEC-5: whitelist de extensiones + Content-Disposition attachment."""

import io
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def storage_local(settings):
    settings.USE_S3 = False
    from apps.core.storage import StorageService

    return StorageService()


# Contenido con cabecera (magic bytes) válida por extensión (M-SEC-8).
_VALID_CONTENT = {
    ".pdf": b"%PDF-1.4 ...",
    ".png": b"\x89PNG\r\n\x1a\n....",
    ".csv": b"col1,col2\n1,2\n",
    ".docx": b"PK\x03\x04 docx",
}


def _file(name, content=b"data"):
    f = io.BytesIO(content)
    f.name = name
    return f


@pytest.mark.parametrize("nombre", ["pagina.html", "icono.svg", "x.htm", "raro.exe", "script.sh"])
def test_upload_extension_no_permitida_rechazada(storage_local, nombre):
    with pytest.raises(ValueError):
        storage_local.upload_file("emp-1", "docs", nombre, _file(nombre))


@pytest.mark.parametrize("nombre", ["factura.pdf", "logo.png", "datos.csv", "doc.docx"])
def test_upload_extension_permitida_ok(storage_local, nombre):
    import os

    content = _VALID_CONTENT[os.path.splitext(nombre)[1]]
    key, _ = storage_local.upload_file("emp-1", "docs", nombre, _file(nombre, content))
    assert key


def test_upload_magic_bytes_no_coinciden_rechazado(storage_local):
    """M-SEC-8: un .pdf cuyo contenido es HTML (no %PDF) se rechaza."""
    with pytest.raises(ValueError):
        storage_local.upload_file("emp-1", "docs", "falso.pdf", _file("falso.pdf", b"<html>evil</html>"))


def test_presigned_fuerza_attachment(settings):
    settings.USE_S3 = True
    from apps.core import storage as storage_mod

    fake_client = MagicMock()
    fake_client.generate_presigned_url.return_value = "https://x/presigned"
    with patch.object(storage_mod, "_get_s3_client", return_value=fake_client):
        svc = storage_mod.StorageService()
        svc.use_s3 = True
        svc.generate_presigned_url("empresas/1/file.pdf")
    params = fake_client.generate_presigned_url.call_args.kwargs["Params"]
    assert params["ResponseContentDisposition"].startswith("attachment")
