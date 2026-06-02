"""
Tests de aislamiento multi-tenant para core (CRIT-1..3, M-API-1, H-SEC-7).

Verifican que:
  1. Los endpoints ``*DetailView`` paralelos (sin filtro de tenant) fueron
     eliminados — sus nombres de URL ya no resuelven (NoReverseMatch) y las
     clases ya no existen en ``apps.core.views``.
  2. El CRUD que ahora maneja el router aplica aislamiento cross-tenant
     (Empresa, Sucursal, Usuario) devolviendo 404 a objetos de otro tenant.
  3. ``usuario_roles_view`` no filtra asignaciones de otra empresa (H-SEC-7).
"""

import pytest

from django.urls import NoReverseMatch, reverse
from rest_framework.test import APIClient

from apps.core.models import Sucursal


# ── 1. Endpoints paralelos eliminados (CRIT-1..3, M-API-1) ─────────────────


@pytest.mark.parametrize(
    "nombre_url",
    ["empresa_detail", "sucursal_detail", "usuario_detail", "departamento_detail"],
)
def test_no_existe_endpoint_detail_paralelo(nombre_url):
    """Los DetailView paralelos sin filtro tenant ya no están registrados."""
    with pytest.raises(NoReverseMatch):
        reverse(nombre_url, args=["00000000-0000-0000-0000-000000000000"])


@pytest.mark.parametrize(
    "clase",
    ["EmpresaDetailView", "UsuarioDetailView", "SucursalDetailView", "DepartamentoDetailView"],
)
def test_clase_detailview_eliminada(clase):
    """Las clases DetailView paralelas ya no existen en core.views."""
    import apps.core.views as core_views

    assert not hasattr(core_views, clase), (
        f"La clase {clase} sigue en core.views — es una bomba de retardo de "
        f"IDOR cross-tenant (usa .objects.all() sin filtro de empresa)."
    )


# ── 2. Aislamiento cross-tenant vía router ─────────────────────────────────


@pytest.fixture
def sucursal_a(db, empresa_a):
    return Sucursal.objects.create(id_empresa=empresa_a, nombre="Suc A", codigo_sucursal="SUCA01")


@pytest.fixture
def sucursal_b(db, empresa_b):
    return Sucursal.objects.create(id_empresa=empresa_b, nombre="Suc B", codigo_sucursal="SUCB01")


@pytest.mark.django_db
class TestAislamientoCoreRouter:
    def test_empresa_cross_tenant_get_404(self, user_a, empresa_a, empresa_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get(f"/api/core/empresas/{empresa_b.id_empresa}/")
        assert resp.status_code == 404

    def test_empresa_cross_tenant_patch_404(self, user_a, empresa_a, empresa_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.patch(
            f"/api/core/empresas/{empresa_b.id_empresa}/",
            {"nombre_legal": "Hackeado"},
            format="json",
        )
        assert resp.status_code == 404
        empresa_b.refresh_from_db()
        assert empresa_b.nombre_legal == "Empresa Beta C.A."

    def test_sucursal_cross_tenant_no_puede_acceder(self, user_a, sucursal_a, sucursal_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        assert client.get(f"/api/core/sucursales/{sucursal_b.id_sucursal}/").status_code == 404
        resp = client.patch(
            f"/api/core/sucursales/{sucursal_b.id_sucursal}/",
            {"nombre": "Hackeado"},
            format="json",
        )
        assert resp.status_code == 404
        sucursal_b.refresh_from_db()
        assert sucursal_b.nombre == "Suc B"

    def test_usuario_cross_tenant_no_puede_modificar(self, user_a, user_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        # UsuariosViewSet: usuario no-superuser solo ve su propio usuario.
        assert client.get(f"/api/core/usuarios/{user_b.id}/").status_code == 404
        resp = client.patch(
            f"/api/core/usuarios/{user_b.id}/",
            {"email": "hacked@evil.com"},
            format="json",
        )
        assert resp.status_code == 404
        user_b.refresh_from_db()
        assert user_b.email == "user_b@empresabeta.com"


# ── 3. usuario_roles_view filtra por empresa (H-SEC-7) ─────────────────────


@pytest.mark.django_db
def test_usuario_roles_no_lista_de_otra_empresa(user_a, user_b):
    """user_a no debe ver asignaciones de roles de usuarios de otra empresa."""
    from apps.core.models import Roles, UsuarioRoles

    rol_b = Roles.objects.create(id_empresa=user_b.empresas.first(), nombre_rol="Rol B")
    UsuarioRoles.objects.create(id_usuario=user_b, id_rol=rol_b)

    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.get("/api/core/usuario_roles/")
    assert resp.status_code == 200
    ids_usuarios = {str(r.get("id_usuario")) for r in resp.data}
    assert str(user_b.id) not in ids_usuarios, "LEAK: usuario_roles expone asignaciones de otra empresa."
