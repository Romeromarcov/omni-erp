"""CRUD del catálogo de proveedores de integración (Panel SaaS).

Gate de escritura (SuperuserWriteMixin): lectura para cualquier autenticado,
escritura (POST/PATCH/DELETE) solo para ``es_superusuario_omni`` (dueño del
software). DELETE es borrado lógico (``activo=False``), no físico.
"""
import pytest
from rest_framework.test import APIClient

from apps.integration_hub.models import ConectorProveedor

pytestmark = pytest.mark.django_db

BASE = "/api/integration-hub/proveedores"


@pytest.fixture
def proveedor(db):
    return ConectorProveedor.objects.create(
        codigo="prov_crud",
        nombre="Prov CRUD",
        capacidades=["contactos"],
        estado="activo",
        activo=True,
    )


@pytest.fixture
def client_tenant(user_a):
    """Usuario tenant normal (no superusuario Omni)."""
    user_a.es_superusuario_omni = False
    user_a.save(update_fields=["es_superusuario_omni"])
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_owner(user_b):
    """Dueño del software (superusuario Omni)."""
    user_b.es_superusuario_omni = True
    user_b.save(update_fields=["es_superusuario_omni"])
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


class TestLecturaProveedores:
    def test_lista_es_array_plano_y_solo_activos(self, client_tenant, proveedor):
        ConectorProveedor.objects.create(codigo="apagado_x", nombre="Apagado", activo=False)
        resp = client_tenant.get(f"{BASE}/")
        assert resp.status_code == 200
        # pagination_class = None → lista plana (contrato del modal Nuevo conector)
        assert isinstance(resp.data, list)
        codigos = [p["codigo"] for p in resp.data]
        assert "prov_crud" in codigos
        assert "apagado_x" not in codigos

    def test_incluir_inactivos_muestra_desactivados(self, client_owner, proveedor):
        ConectorProveedor.objects.create(codigo="apagado_y", nombre="Apagado", activo=False)
        resp = client_owner.get(f"{BASE}/?incluir_inactivos=true")
        assert resp.status_code == 200
        assert "apagado_y" in [p["codigo"] for p in resp.data]

    def test_requiere_autenticacion(self, proveedor):
        resp = APIClient().get(f"{BASE}/")
        assert resp.status_code in (401, 403)


class TestEscrituraSoloOwner:
    PAYLOAD = {"codigo": "nuevo_prov", "nombre": "Nuevo Proveedor"}

    def test_tenant_no_puede_crear(self, client_tenant):
        resp = client_tenant.post(f"{BASE}/", self.PAYLOAD, format="json")
        assert resp.status_code == 403
        assert not ConectorProveedor.objects.filter(codigo="nuevo_prov").exists()

    def test_owner_puede_crear(self, client_owner):
        resp = client_owner.post(f"{BASE}/", self.PAYLOAD, format="json")
        assert resp.status_code == 201
        assert ConectorProveedor.objects.filter(codigo="nuevo_prov").exists()

    def test_tenant_no_puede_editar(self, client_tenant, proveedor):
        resp = client_tenant.patch(
            f"{BASE}/{proveedor.pk}/", {"nombre": "Hackeado"}, format="json"
        )
        assert resp.status_code == 403
        proveedor.refresh_from_db()
        assert proveedor.nombre == "Prov CRUD"

    def test_owner_puede_editar(self, client_owner, proveedor):
        resp = client_owner.patch(
            f"{BASE}/{proveedor.pk}/", {"nombre": "Editado"}, format="json"
        )
        assert resp.status_code == 200
        proveedor.refresh_from_db()
        assert proveedor.nombre == "Editado"

    def test_delete_es_borrado_logico(self, client_owner, proveedor):
        resp = client_owner.delete(f"{BASE}/{proveedor.pk}/")
        assert resp.status_code == 204
        proveedor.refresh_from_db()
        # No se borra físicamente (FK PROTECT desde instancias): solo activo=False
        assert proveedor.activo is False

    def test_tenant_no_puede_borrar(self, client_tenant, proveedor):
        resp = client_tenant.delete(f"{BASE}/{proveedor.pk}/")
        assert resp.status_code == 403
        proveedor.refresh_from_db()
        assert proveedor.activo is True


class TestValidacionCodigo:
    def test_codigo_invalido_rechazado(self, client_owner):
        resp = client_owner.post(
            f"{BASE}/", {"codigo": "Odoo Producción!", "nombre": "X"}, format="json"
        )
        assert resp.status_code == 400
        assert "codigo" in resp.data

    def test_codigo_se_normaliza_a_minusculas(self, client_owner):
        resp = client_owner.post(
            f"{BASE}/", {"codigo": "MiConector", "nombre": "X"}, format="json"
        )
        # Se normaliza a minúsculas antes de guardar (debe coincidir con el registry).
        assert resp.status_code == 201
        assert resp.data["codigo"] == "miconector"


class TestValidacionCapacidadesYVersiones:
    """capacidades y versiones_soportadas deben ser listas (no objeto/escalar)."""

    def test_capacidades_no_lista_rechazada(self, client_owner):
        resp = client_owner.post(
            f"{BASE}/",
            {"codigo": "cap_bad", "nombre": "X", "capacidades": {"no": "lista"}},
            format="json",
        )
        assert resp.status_code == 400
        assert "capacidades" in resp.data
        assert not ConectorProveedor.objects.filter(codigo="cap_bad").exists()

    def test_capacidades_lista_aceptada(self, client_owner):
        resp = client_owner.post(
            f"{BASE}/",
            {"codigo": "cap_ok", "nombre": "X", "capacidades": ["contactos"]},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["capacidades"] == ["contactos"]

    def test_versiones_no_lista_rechazada(self, client_owner):
        resp = client_owner.post(
            f"{BASE}/",
            {"codigo": "ver_bad", "nombre": "X", "versiones_soportadas": "v17"},
            format="json",
        )
        assert resp.status_code == 400
        assert "versiones_soportadas" in resp.data
        assert not ConectorProveedor.objects.filter(codigo="ver_bad").exists()

    def test_versiones_lista_aceptada(self, client_owner):
        resp = client_owner.post(
            f"{BASE}/",
            {"codigo": "ver_ok", "nombre": "X", "versiones_soportadas": ["17", "18"]},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["versiones_soportadas"] == ["17", "18"]
