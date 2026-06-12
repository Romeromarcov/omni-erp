"""
S1 Hardening (Plan 05 — P1-1 / P1-3 / P1-4).

P1-1 · Throttling DRF:
  - tasas configurables presentes (incl. scope 'escritura')
  - EscrituraRateThrottle: no cuenta GET, devuelve 429 al exceder escrituras

P1-3 · django-axes:
  - configuración activa (app, backend, middleware, lockout usuario+IP)
  - tras N fallos de login la combinación usuario+IP queda bloqueada (429)
    incluso con la contraseña correcta; el mensaje NO filtra si el usuario existe
  - otro usuario desde la misma IP no queda bloqueado
  - política de contraseñas: mínimo 12 caracteres

P1-4 · Revocación JWT:
  - blacklist de SimpleJWT activa (app + rotación + access TTL corto)
  - logout con cookie httpOnly revoca el refresh: el reuse falla con 401

Anti-flakiness (R-PROC-4): los tests de throttling usan throttles autocontenidos
con APIRequestFactory (mismo patrón que test_p11_throttling_global.py) y el
conftest limpia la cache entre tests. django-axes usa su handler de base de
datos, aislado por la transacción de cada test.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.core.throttling import EscrituraRateThrottle

LOGIN_URL = "/api/auth/login/"
PASSWORD = "s1_Password_larga_123"


@pytest.fixture(autouse=True)
def _limpiar_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def usuario(db):
    User = get_user_model()
    return User.objects.create_user(
        username="s1_user",
        password=PASSWORD,
        email="s1@test.com",
        is_active=True,
    )


# ═════════════════════════ P1-1 · Throttling ═════════════════════════════════


class _Escritura3Min(EscrituraRateThrottle):
    rate = "3/min"


class _VistaEscritura(APIView):
    throttle_classes = [_Escritura3Min]

    def get(self, request):
        return Response({"ok": True})

    def post(self, request):
        return Response({"ok": True})


class TestP11ThrottleEscritura:
    def test_tasas_configuradas_incluyen_escritura(self, settings):
        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        for clave in ("anon", "user", "signup", "escritura"):
            assert clave in rates, f"Falta tasa '{clave}'"

    def test_get_no_consume_cuota_de_escritura(self, usuario):
        factory = APIRequestFactory()
        view = _VistaEscritura.as_view()
        for _ in range(10):
            req = factory.get("/_s1-probe/")
            force_authenticate(req, user=usuario)
            assert view(req).status_code == 200

    def test_post_throttled_al_exceder_limite(self, usuario):
        factory = APIRequestFactory()
        view = _VistaEscritura.as_view()
        for i in range(3):
            req = factory.post("/_s1-probe/")
            force_authenticate(req, user=usuario)
            assert view(req).status_code != 429, f"POST #{i + 1} prematuro"
        req = factory.post("/_s1-probe/")
        force_authenticate(req, user=usuario)
        assert view(req).status_code == 429

    def test_viewsets_de_pago_declaran_throttle_escritura(self):
        from apps.cuentas_por_cobrar.views_abono import AbonoCxCViewSet
        from apps.cuentas_por_pagar.views_abono import AbonoCxPViewSet
        from apps.finanzas.views import PagoViewSet

        for vs in (PagoViewSet, AbonoCxCViewSet, AbonoCxPViewSet):
            assert any(
                issubclass(t, EscrituraRateThrottle) for t in vs.throttle_classes
            ), f"{vs.__name__} no tiene EscrituraRateThrottle"


# ═════════════════════════ P1-3 · django-axes ════════════════════════════════


class TestP13Axes:
    def test_configuracion_axes_activa(self, settings):
        assert "axes" in settings.INSTALLED_APPS
        assert settings.AUTHENTICATION_BACKENDS[0] == (
            "axes.backends.AxesStandaloneBackend"
        )
        assert "axes.middleware.AxesMiddleware" in settings.MIDDLEWARE
        assert settings.AXES_FAILURE_LIMIT >= 3
        # Lockout por la COMBINACIÓN usuario+IP (lista anidada = AND)
        assert settings.AXES_LOCKOUT_PARAMETERS == [["username", "ip_address"]]

    def test_bloqueo_tras_n_fallos_y_mensaje_generico(self, usuario, settings):
        """
        Tras AXES_FAILURE_LIMIT fallos, el login devuelve 429 incluso con la
        contraseña CORRECTA, y el mensaje no revela si el usuario existe.

        Se desactiva django-ratelimit (SEC-07, 5/min por IP) con su switch
        oficial RATELIMIT_ENABLE para poder observar el lockout de axes con
        la MISMA IP sin el 429 del otro mecanismo.
        """
        client = APIClient()
        settings.RATELIMIT_ENABLE = False
        for _ in range(settings.AXES_FAILURE_LIMIT):
            resp = client.post(
                LOGIN_URL,
                {"username": usuario.username, "password": "incorrecta-xyz"},
                format="json",
            )
            # El intento N (el que alcanza el límite) ya responde 429
            # vía AxesMiddleware; los anteriores 401.
            assert resp.status_code in (401, 429)

        # Con la contraseña correcta: bloqueado (429) y mensaje genérico
        resp = client.post(
            LOGIN_URL,
            {"username": usuario.username, "password": PASSWORD},
            format="json",
        )
        assert resp.status_code == 429
        error = resp.json()["error"].lower()
        assert "usuario" not in error and usuario.username not in error
        assert "existe" not in error

    def test_lockout_es_por_usuario_mas_ip(self, usuario, settings):
        """Otro username desde la misma IP NO queda bloqueado."""
        User = get_user_model()
        otro = User.objects.create_user(
            username="s1_otro_user",
            password=PASSWORD,
            email="s1otro@test.com",
            is_active=True,
        )
        client = APIClient()
        settings.RATELIMIT_ENABLE = False  # neutraliza SEC-07 (ver test previo)
        for _ in range(settings.AXES_FAILURE_LIMIT):
            client.post(
                LOGIN_URL,
                {"username": usuario.username, "password": "incorrecta-xyz"},
                format="json",
            )
        # El otro usuario entra normalmente
        resp = client.post(
            LOGIN_URL,
            {"username": otro.username, "password": PASSWORD},
            format="json",
        )
        assert resp.status_code == 200
        assert "access" in resp.json()

    def test_login_fallido_no_revela_existencia_de_usuario(self, usuario):
        """Mismo mensaje para usuario inexistente y contraseña errada."""
        client = APIClient()
        r1 = client.post(
            LOGIN_URL,
            {"username": "no_existe_xyz", "password": "loquesea-123"},
            format="json",
        )
        cache.clear()  # no mezclar contadores de ratelimit entre requests
        r2 = client.post(
            LOGIN_URL,
            {"username": usuario.username, "password": "incorrecta-xyz"},
            format="json",
        )
        assert r1.status_code == r2.status_code == 401
        assert r1.json()["error"] == r2.json()["error"]

    def test_password_minimo_12_caracteres(self, settings):
        assert settings.PASSWORD_MIN_LENGTH >= 12
        with pytest.raises(DjangoValidationError):
            validate_password("Corta123!")  # 9 chars
        # Una contraseña larga y no común pasa
        validate_password("frase-larga-sin-numeros-obvios-77")


# ═════════════════════════ P1-4 · Revocación JWT ═════════════════════════════


class TestP14RevocacionJWT:
    def test_configuracion_blacklist_activa(self, settings):
        assert "rest_framework_simplejwt.token_blacklist" in settings.INSTALLED_APPS
        assert settings.SIMPLE_JWT["ROTATE_REFRESH_TOKENS"] is True
        assert settings.SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"] is True
        # TTL de access corto (≤ 15 min)
        assert settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"] <= timedelta(minutes=15)

    def test_logout_con_cookie_revoca_refresh(self, usuario):
        """
        Flujo real SEC-03: login deja el refresh en cookie httpOnly; logout lo
        blacklistea; el reuse del refresh (vía cookie) falla con 401.
        """
        client = APIClient()
        resp = client.post(
            LOGIN_URL,
            {"username": usuario.username, "password": PASSWORD},
            format="json",
        )
        assert resp.status_code == 200
        assert "refresh" not in resp.json()  # nunca en el body
        refresh_cookie = resp.cookies.get("refresh_token")
        assert refresh_cookie is not None and refresh_cookie.value
        assert refresh_cookie["httponly"]
        access = resp.json()["access"]

        # Logout (la cookie viaja sola en el client)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        resp = client.post("/api/auth/logout/", {}, format="json")
        assert resp.status_code == 200

        # Reuse del refresh revocado → 401
        client.credentials()
        cache.clear()  # el ratelimit del refresh no debe interferir
        client.cookies["refresh_token"] = refresh_cookie.value
        resp = client.post("/api/auth/token/refresh/", {}, format="json")
        assert resp.status_code == 401

    def test_refresh_valido_sigue_funcionando_antes_del_logout(self, usuario):
        """Control: sin logout, el refresh por cookie renueva el access."""
        client = APIClient()
        resp = client.post(
            LOGIN_URL,
            {"username": usuario.username, "password": PASSWORD},
            format="json",
        )
        assert resp.status_code == 200
        cache.clear()
        resp = client.post("/api/auth/token/refresh/", {}, format="json")
        assert resp.status_code == 200
        assert "access" in resp.json()
