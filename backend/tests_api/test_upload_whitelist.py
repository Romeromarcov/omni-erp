"""H-SEC-5: whitelist de extensiones + Content-Disposition attachment."""

import io
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def storage_local(settings):
    settings.USE_S3 = False
    from apps.core.storage import StorageService

    return StorageService()


def _file(name):
    f = io.BytesIO(b"data")
    f.name = name
    return f


@pytest.mark.parametrize("nombre", ["pagina.html", "icono.svg", "x.htm", "raro.exe", "script.sh"])
def test_upload_extension_no_permitida_rechazada(storage_local, nombre):
    with pytest.raises(ValueError):
        storage_local.upload_file("emp-1", "docs", nombre, _file(nombre))


@pytest.mark.parametrize("nombre", ["factura.pdf", "logo.png", "datos.csv", "doc.docx"])
def test_upload_extension_permitida_ok(storage_local, nombre):
    key, _ = storage_local.upload_file("emp-1", "docs", nombre, _file(nombre))
    assert key


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
