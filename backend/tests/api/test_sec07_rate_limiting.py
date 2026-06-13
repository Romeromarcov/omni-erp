"""
SEC-07 — Rate limiting en endpoints de login.

DoD:
  - /api/auth/login/    : bloqueado al 6to POST desde la misma IP (límite 5/min)
  - /api/auth/token/    : bloqueado al 6to POST desde la misma IP (límite 5/min)
  - Respuesta 429 incluye campo "error" con mensaje legible
  - Logins exitosos también cuentan para el límite
"""

import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

# Timestamp fijo, lejos del borde del minuto (30 segundos dentro del minuto).
# Previene que las ventanas de rate-limit cambien entre requests del mismo test.
_FIXED_TS = 1_748_000_030.0


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _freeze_ratelimit_window():
    """
    Congela el reloj que usa django-ratelimit para calcular la ventana de
    tiempo, evitando fallos intermitentes por cruce de minuto.
    """
    import django_ratelimit.core as rl_core

    with patch.object(rl_core.time, "time", return_value=_FIXED_TS):
        yield


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def usuario_activo(db):
    """Usuario válido para probar que logins exitosos también cuentan."""
    User = get_user_model()
    return User.objects.create_user(
        username="sec07_user",
        password="sec07_Password!",
        email="sec07@test.com",
        is_active=True,
    )


# ── /api/auth/login/ ─────────────────────────────────────────────────────────


class TestSEC07LoginView:
    """Rate limiting en /api/auth/login/ (FBV login_view)."""

    URL = "/api/auth/login/"

    def _post(self, client, username="no_existe", password="wrong"):
        return client.post(
            self.URL,
            {"username": username, "password": password},
            format="json",
        )

    def test_primeros_cinco_intentos_no_son_bloqueados(self, api_client, db):
        """Los 5 primeros intentos deben pasar (401, no 429)."""
        for i in range(5):
            resp = self._post(api_client)
            assert resp.status_code != 429, (
                f"Intento {i + 1} fue bloqueado con 429, debería pasar."
            )

    def test_sexto_intento_retorna_429(self, api_client, db):
        """El 6to intento consecutivo desde la misma IP devuelve 429."""
        for _ in range(5):
            self._post(api_client)

        resp = self._post(api_client)
        assert resp.status_code == 429

    def test_respuesta_429_contiene_campo_error(self, api_client, db):
        """La respuesta 429 incluye un campo 'error' con mensaje legible."""
        for _ in range(5):
            self._post(api_client)

        resp = self._post(api_client)
        assert resp.status_code == 429
        data = resp.json()
        assert "error" in data
        assert len(data["error"]) > 0

    def test_login_exitoso_cuenta_para_el_limite(self, api_client, usuario_activo):
        """Los logins exitosos también incrementan el contador de rate limit."""
        # 5 logins exitosos
        for _ in range(5):
            resp = self._post(api_client, usuario_activo.username, "sec07_Password!")
            assert resp.status_code == 200

        # El 6to (también exitoso en credenciales) debe ser bloqueado
        resp = self._post(api_client, usuario_activo.username, "sec07_Password!")
        assert resp.status_code == 429

    def test_intento_bloqueado_no_autentica(self, api_client, usuario_activo):
        """Un intento bloqueado por rate limit devuelve 429, no 200 ni 401."""
        for _ in range(5):
            self._post(api_client)

        resp = self._post(api_client, usuario_activo.username, "sec07_Password!")
        # No debe autenticar aunque las credenciales sean válidas
        assert resp.status_code == 429
        assert "access" not in resp.json()


# ── /api/auth/token/ ─────────────────────────────────────────────────────────


class TestSEC07TokenView:
    """Rate limiting en /api/auth/token/ (CBV CustomTokenObtainPairView)."""

    URL = "/api/auth/token/"

    def _post(self, client, username="no_existe", password="wrong"):
        return client.post(
            self.URL,
            {"username": username, "password": password},
            format="json",
        )

    def test_primeros_cinco_intentos_no_son_bloqueados(self, api_client, db):
        """Los 5 primeros intentos deben pasar (401, no 429)."""
        for i in range(5):
            resp = self._post(api_client)
            assert resp.status_code != 429, (
                f"Intento {i + 1} fue bloqueado con 429, debería pasar."
            )

    def test_sexto_intento_retorna_429(self, api_client, db):
        """El 6to intento consecutivo desde la misma IP devuelve 429."""
        for _ in range(5):
            self._post(api_client)

        resp = self._post(api_client)
        assert resp.status_code == 429

    def test_respuesta_429_contiene_campo_error(self, api_client, db):
        """La respuesta 429 incluye un campo 'error' con mensaje legible."""
        for _ in range(5):
            self._post(api_client)

        resp = self._post(api_client)
        assert resp.status_code == 429
        data = resp.json()
        assert "error" in data

    def test_login_exitoso_cuenta_para_el_limite(self, api_client, usuario_activo):
        """Los logins exitosos también incrementan el contador de rate limit."""
        for _ in range(5):
            resp = self._post(api_client, usuario_activo.username, "sec07_Password!")
            assert resp.status_code == 200

        resp = self._post(api_client, usuario_activo.username, "sec07_Password!")
        assert resp.status_code == 429
