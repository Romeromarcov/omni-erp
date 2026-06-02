"""H-API-3: UsuariosSerializer expone una whitelist segura de campos."""

import pytest

from rest_framework.test import APIClient


PROHIBIDOS = {"is_superuser", "is_staff", "last_login", "groups", "user_permissions"}


@pytest.mark.django_db
def test_usuario_serializer_no_expone_campos_de_privilegio(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.get("/api/core/usuarios/me/")
    assert resp.status_code == 200
    assert PROHIBIDOS.isdisjoint(resp.data.keys()), (
        f"UsuariosSerializer expone campos prohibidos: {PROHIBIDOS & set(resp.data.keys())}"
    )
    assert "password" not in resp.data


@pytest.mark.django_db
def test_usuario_serializer_no_acepta_is_staff_desde_cliente(user_a):
    """Aunque el cliente envíe is_staff/is_superuser, no se asignan."""
    client = APIClient()
    client.force_authenticate(user=user_a)
    # PATCH sobre el propio usuario vía el ViewSet (no-superuser solo ve el suyo).
    resp = client.patch(
        f"/api/core/usuarios/{user_a.id}/",
        {"is_staff": True, "is_superuser": True, "first_name": "Nuevo"},
        format="json",
    )
    assert resp.status_code in (200, 403, 404)
    user_a.refresh_from_db()
    assert user_a.is_staff is False
    assert user_a.is_superuser is False
