"""
Backfill de cobertura — apps/core/auth_views.py (plan "Cero Dudas", COV/auth).

Complementa ``test_auth_completo.py`` (que cubre ``token_obtain_pair``, ``logout``,
``token_refresh`` y ``change_password``) ejercitando los endpoints que quedaban
**sin cubrir**, todos de seguridad/authz:

- ``login_view`` (``/api/auth/login/``) — el login legacy SIN ``device_fingerprint``:
  feliz (200 + cookie httpOnly de refresh), credenciales faltantes (400), inválidas
  (401), usuario inactivo (401) y rate-limit (429).
- ``verify_token_view`` — 200 autenticado / 401 sin token.
- ``user_profile_view`` — 200 autenticado / 401 sin token.
- ``update_profile_view`` — 200 actualizando campos permitidos, 200 no-op (sin campos),
  401 sin token; verifica que SOLO se tocan los campos de la allowlist.
- ``refresh_token_view`` — rotación de refresh (cookie nueva) y rate-limit (429).

Aserciones sobre valores/efectos exactos (cookie presente, campo persistido) para que
sirvan también de runner de mutación. Fixtures (``user_a``, ``empresa_a``,
``moneda_usd``) vienen del conftest de ``tests_api/``.
"""
import pytest
from rest_framework.test import APIClient

from rest_framework_simplejwt.tokens import RefreshToken

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/token/refresh/"
VERIFY_URL = "/api/auth/token/verify/"
PROFILE_URL = "/api/auth/profile/"
PROFILE_UPDATE_URL = "/api/auth/profile/update/"

# Contraseña fijada por el fixture user_a del conftest de tests_api/.
PASSWORD = "testpass123"


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


# ── login_view (/api/auth/login/) ─────────────────────────────────────────────

class TestLoginView:
    def test_login_exitoso_200_y_cookie_refresh(self, user_a):
        resp = APIClient().post(
            LOGIN_URL,
            {"username": user_a.username, "password": PASSWORD},
            format="json",
        )
        assert resp.status_code == 200
        body = resp.json()
        # El access viene en el body; el refresh NUNCA (va en cookie httpOnly — SEC-03).
        assert "access" in body
        assert "refresh" not in body
        assert body["user"]["username"] == user_a.username
        cookie = resp.cookies.get("refresh_token")
        assert cookie is not None
        assert cookie["httponly"] is True
        assert cookie["path"] == "/api/auth/"

    def test_login_actualiza_last_login(self, user_a):
        assert user_a.last_login is None
        APIClient().post(
            LOGIN_URL, {"username": user_a.username, "password": PASSWORD}, format="json"
        )
        user_a.refresh_from_db()
        assert user_a.last_login is not None

    def test_login_sin_credenciales_400(self):
        resp = APIClient().post(LOGIN_URL, {"username": ""}, format="json")
        assert resp.status_code == 400

    def test_login_credenciales_invalidas_401(self, user_a):
        resp = APIClient().post(
            LOGIN_URL, {"username": user_a.username, "password": "mala"}, format="json"
        )
        assert resp.status_code == 401

    def test_login_usuario_inactivo_401(self, user_a):
        user_a.is_active = False
        user_a.save(update_fields=["is_active"])
        resp = APIClient().post(
            LOGIN_URL, {"username": user_a.username, "password": PASSWORD}, format="json"
        )
        # authenticate() devuelve None para inactivos → 401 credenciales inválidas.
        assert resp.status_code == 401

    def test_login_rate_limit_429(self, user_a):
        """SEC-07: >5 POST/min por IP → 429 (con credenciales inválidas para no
        depender del flujo feliz)."""
        client = APIClient()
        codigos = [
            client.post(
                LOGIN_URL, {"username": user_a.username, "password": "x"}, format="json"
            ).status_code
            for _ in range(7)
        ]
        assert 429 in codigos


# ── verify_token_view ─────────────────────────────────────────────────────────

class TestVerifyToken:
    def test_verify_autenticado_200(self, client_a, user_a):
        resp = client_a.get(VERIFY_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["user"]["username"] == user_a.username

    def test_verify_sin_token_401(self):
        assert APIClient().get(VERIFY_URL).status_code == 401


# ── user_profile_view ─────────────────────────────────────────────────────────

class TestUserProfile:
    def test_profile_autenticado_200(self, client_a, user_a):
        resp = client_a.get(PROFILE_URL)
        assert resp.status_code == 200
        assert resp.json()["username"] == user_a.username

    def test_profile_sin_token_401(self):
        assert APIClient().get(PROFILE_URL).status_code == 401


# ── update_profile_view ───────────────────────────────────────────────────────

class TestUpdateProfile:
    def test_update_campos_permitidos_200(self, client_a, user_a):
        resp = client_a.put(
            PROFILE_UPDATE_URL,
            {"first_name": "Nuevo", "last_name": "Apellido", "email": "nuevo@a.test"},
            format="json",
        )
        assert resp.status_code == 200
        user_a.refresh_from_db()
        assert user_a.first_name == "Nuevo"
        assert user_a.last_name == "Apellido"
        assert user_a.email == "nuevo@a.test"

    def test_update_ignora_campos_fuera_de_allowlist(self, client_a, user_a):
        """Campos como is_staff/username NO deben poder actualizarse por aquí."""
        resp = client_a.put(
            PROFILE_UPDATE_URL,
            {"is_staff": True, "username": "hacker", "first_name": "Ok"},
            format="json",
        )
        assert resp.status_code == 200
        user_a.refresh_from_db()
        assert user_a.is_staff is False
        assert user_a.username == "user_empresa_a"
        assert user_a.first_name == "Ok"

    def test_update_sin_campos_es_noop_200(self, client_a, user_a):
        original = user_a.first_name
        resp = client_a.put(PROFILE_UPDATE_URL, {}, format="json")
        assert resp.status_code == 200
        user_a.refresh_from_db()
        assert user_a.first_name == original

    def test_update_sin_token_401(self):
        assert APIClient().put(PROFILE_UPDATE_URL, {}, format="json").status_code == 401


# ── refresh_token_view ────────────────────────────────────────────────────────

class TestRefreshRotation:
    def test_refresh_con_rotacion_emite_nueva_cookie(self, settings, user_a):
        """Con ROTATE_REFRESH_TOKENS, el refresh entrega un nuevo refresh en cookie
        httpOnly (nunca en el body)."""
        settings.SIMPLE_JWT = {
            **settings.SIMPLE_JWT,
            "ROTATE_REFRESH_TOKENS": True,
            "BLACKLIST_AFTER_ROTATION": True,
        }
        refresh = RefreshToken.for_user(user_a)
        resp = APIClient().post(REFRESH_URL, {"refresh": str(refresh)}, format="json")
        assert resp.status_code == 200
        assert "access" in resp.json()
        cookie = resp.cookies.get("refresh_token")
        assert cookie is not None
        assert cookie["httponly"] is True

    def test_refresh_rate_limit_429(self, user_a):
        """M-SEC-13: >20 POST/min por IP al refresh → 429."""
        client = APIClient()
        refresh = str(RefreshToken.for_user(user_a))
        codigos = [
            client.post(REFRESH_URL, {"refresh": refresh}, format="json").status_code
            for _ in range(22)
        ]
        assert 429 in codigos
