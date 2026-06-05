"""
Tests de aislamiento multi-tenant — módulo gestion_documental (R-CODE-1).

Verifica que un usuario de Empresa A NO puede ver ni modificar Carpetas ni
Documentos de Empresa B.

Un FAIL = leak de datos entre tenants → bloquea merge.
"""

import pytest
from rest_framework.test import APIClient

from apps.core.models import Usuarios
from apps.gestion_documental.models import Carpeta, Documento

URL_CARPETAS = "/api/gestion-documental/carpetas/"
URL_DOCUMENTOS = "/api/gestion-documental/documentos/"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def carpeta_a(db, empresa_a, user_a):
    return Carpeta.objects.create(
        id_empresa=empresa_a,
        nombre_carpeta="Carpeta Alpha",
        id_usuario_creacion=user_a,
        es_publica=False,
    )


@pytest.fixture
def carpeta_b(db, empresa_b, user_b):
    return Carpeta.objects.create(
        id_empresa=empresa_b,
        nombre_carpeta="Carpeta Beta",
        id_usuario_creacion=user_b,
        es_publica=False,
    )


@pytest.fixture
def documento_a(db, empresa_a, user_a, carpeta_a):
    return Documento.objects.create(
        id_empresa=empresa_a,
        nombre_archivo="contrato_alpha.pdf",
        tipo_contenido="application/pdf",
        tamano_bytes=1024,
        ruta_almacenamiento="alpha/contratos/contrato_alpha.pdf",
        id_usuario_subida=user_a,
        id_carpeta=carpeta_a,
    )


@pytest.fixture
def documento_b(db, empresa_b, user_b, carpeta_b):
    return Documento.objects.create(
        id_empresa=empresa_b,
        nombre_archivo="contrato_beta.pdf",
        tipo_contenido="application/pdf",
        tamano_bytes=2048,
        ruta_almacenamiento="beta/contratos/contrato_beta.pdf",
        id_usuario_subida=user_b,
        id_carpeta=carpeta_b,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Carpeta
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAislamientoCarpetas:
    """R-CODE-1 :: gestion_documental.Carpeta"""

    def test_list_solo_devuelve_carpetas_propias(self, user_a, carpeta_a, carpeta_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(URL_CARPETAS)
        assert resp.status_code == 200

        data = resp.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_carpeta"]) for r in resultados}

        assert str(carpeta_a.id_carpeta) in ids, "La carpeta propia de Empresa A no aparece en el listado."
        assert (
            str(carpeta_b.id_carpeta) not in ids
        ), "LEAK: carpeta de Empresa B aparece en listado de Empresa A."

    def test_get_carpeta_ajena_devuelve_404(self, user_a, carpeta_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(f"{URL_CARPETAS}{carpeta_b.id_carpeta}/")
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al acceder a carpeta de Empresa B."

    def test_patch_carpeta_ajena_devuelve_404(self, user_a, carpeta_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.patch(
            f"{URL_CARPETAS}{carpeta_b.id_carpeta}/",
            {"nombre_carpeta": "HACK"},
            format="json",
        )
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al parchear carpeta de Empresa B."

        carpeta_b.refresh_from_db()
        assert (
            carpeta_b.nombre_carpeta == "Carpeta Beta"
        ), "CRÍTICO: el nombre de la carpeta de Empresa B fue modificado desde Empresa A."


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Documento
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAislamientoDocumentos:
    """R-CODE-1 :: gestion_documental.Documento"""

    def test_list_solo_devuelve_documentos_propios(self, user_a, documento_a, documento_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(URL_DOCUMENTOS)
        assert resp.status_code == 200

        data = resp.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_documento"]) for r in resultados}

        assert str(documento_a.id_documento) in ids, "El documento propio de Empresa A no aparece en el listado."
        assert (
            str(documento_b.id_documento) not in ids
        ), "LEAK: documento de Empresa B aparece en listado de Empresa A."

    def test_get_documento_ajeno_devuelve_404(self, user_a, documento_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(f"{URL_DOCUMENTOS}{documento_b.id_documento}/")
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al acceder a documento de Empresa B."
