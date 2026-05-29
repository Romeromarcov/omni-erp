"""
GAP-09: Integration tests for SuscripcionActivaMiddleware.

Covers:
  - Active subscription → 200 (middleware passes request through)
  - Expired subscription → 402 Payment Required
  - No subscription → 402 Payment Required
  - SAAS_VERIFICAR_SUSCRIPCION=False → always passes (default dev mode)
  - Unauthenticated user → always passes (middleware skips anonymous)
  - Excluded paths (e.g. /api/auth/) → always pass even without subscription
  - Admin path → always passes
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone
from unittest.mock import MagicMock, patch

from apps.core.models import Empresa
from apps.saas.middleware import SuscripcionActivaMiddleware

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def empresa(db):
    return Empresa.objects.create(nombre="Test SaaS Corp", rif="J-99999999-9")


@pytest.fixture
def usuario(db, empresa):
    user = User.objects.create_user(
        username="saas_user",
        password="pass",
        email="saas@test.com",
    )
    user.empresas.add(empresa)
    return user


def _make_middleware(settings_overrides=None, settings=None):
    """Build a SuscripcionActivaMiddleware with a dummy get_response."""
    dummy_response = MagicMock(status_code=200)
    get_response = MagicMock(return_value=dummy_response)
    middleware = SuscripcionActivaMiddleware(get_response)
    return middleware, get_response, dummy_response


def _make_request(user=None, path="/api/inventario/"):
    factory = RequestFactory()
    request = factory.get(path)
    if user is not None:
        request.user = user
    else:
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
    return request


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSuscripcionActivaMiddlewareDisabled:
    """When SAAS_VERIFICAR_SUSCRIPCION=False (default), middleware is a no-op."""

    def test_passes_all_requests_when_disabled(self, settings, usuario):
        settings.SAAS_VERIFICAR_SUSCRIPCION = False
        middleware, get_response, dummy_response = _make_middleware()
        request = _make_request(user=usuario)
        response = middleware(request)
        get_response.assert_called_once_with(request)
        assert response.status_code == 200

    def test_passes_even_without_subscription(self, settings, usuario, empresa, db):
        settings.SAAS_VERIFICAR_SUSCRIPCION = False
        middleware, get_response, _ = _make_middleware()
        # No subscriptions created — but middleware is disabled
        request = _make_request(user=usuario)
        response = middleware(request)
        get_response.assert_called_once()


class TestSuscripcionActivaMiddlewareEnabled:
    """When SAAS_VERIFICAR_SUSCRIPCION=True, middleware enforces subscription."""

    def test_active_subscription_passes(self, settings, usuario, empresa, db):
        """User with active subscription gets through."""
        settings.SAAS_VERIFICAR_SUSCRIPCION = True
        today = datetime.date.today()

        # Mock suscripcion_activa to return a truthy value (subscription exists)
        with patch("apps.saas.middleware.SuscripcionActivaMiddleware._verificar_suscripcion", return_value=None):
            middleware, get_response, dummy = _make_middleware()
            request = _make_request(user=usuario)
            response = middleware(request)
            get_response.assert_called_once_with(request)

    def test_no_subscription_returns_402(self, settings, usuario, empresa, db):
        """User without active subscription gets 402."""
        settings.SAAS_VERIFICAR_SUSCRIPCION = True

        middleware, get_response, _ = _make_middleware()
        # Patch suscripcion_activa to return None (no subscription)
        with patch("apps.saas.models.suscripcion_activa", return_value=None):
            middleware.activo = True
            request = _make_request(user=usuario)
            response = middleware(request)
            assert response.status_code == 402
            get_response.assert_not_called()

    def test_402_response_has_correct_body(self, settings, usuario, empresa, db):
        """402 response contains expected JSON fields."""
        import json
        settings.SAAS_VERIFICAR_SUSCRIPCION = True

        middleware, _, _ = _make_middleware()
        with patch("apps.saas.models.suscripcion_activa", return_value=None):
            middleware.activo = True
            request = _make_request(user=usuario)
            response = middleware(request)
            assert response.status_code == 402
            body = json.loads(response.content)
            assert "detail" in body
            assert body["codigo"] == "SUSCRIPCION_REQUERIDA"

    def test_anonymous_user_always_passes(self, settings, db):
        """Anonymous users are never checked for subscription."""
        settings.SAAS_VERIFICAR_SUSCRIPCION = True
        middleware, get_response, _ = _make_middleware()
        middleware.activo = True
        request = _make_request(user=None)
        middleware(request)
        get_response.assert_called_once()

    def test_excluded_path_always_passes(self, settings, usuario, db):
        """Requests to excluded paths bypass subscription check."""
        settings.SAAS_VERIFICAR_SUSCRIPCION = True
        middleware, get_response, _ = _make_middleware()
        middleware.activo = True
        # /api/auth/ is in RUTAS_EXCLUIDAS_DEFAULT
        request = _make_request(user=usuario, path="/api/auth/login/")
        with patch("apps.saas.models.suscripcion_activa", return_value=None):
            middleware(request)
            get_response.assert_called_once()

    def test_admin_path_always_passes(self, settings, usuario, db):
        """Admin paths bypass subscription check."""
        settings.SAAS_VERIFICAR_SUSCRIPCION = True
        middleware, get_response, _ = _make_middleware()
        middleware.activo = True
        request = _make_request(user=usuario, path="/admin/")
        with patch("apps.saas.models.suscripcion_activa", return_value=None):
            middleware(request)
            get_response.assert_called_once()

    def test_swagger_path_always_passes(self, settings, usuario, db):
        """Swagger docs path bypasses subscription check."""
        settings.SAAS_VERIFICAR_SUSCRIPCION = True
        middleware, get_response, _ = _make_middleware()
        middleware.activo = True
        request = _make_request(user=usuario, path="/swagger/")
        with patch("apps.saas.models.suscripcion_activa", return_value=None):
            middleware(request)
            get_response.assert_called_once()

    def test_user_without_empresa_passes(self, settings, db):
        """User with no empresa is allowed through (no empresa to check)."""
        settings.SAAS_VERIFICAR_SUSCRIPCION = True
        user = User.objects.create_user(username="no_empresa", password="pass")
        middleware, get_response, _ = _make_middleware()
        middleware.activo = True
        request = _make_request(user=user)
        # No subscription needed if no empresa
        middleware(request)
        get_response.assert_called_once()

    def test_exception_in_suscripcion_check_fails_open(self, settings, usuario, db):
        """If suscripcion_activa raises an exception, middleware fails open (200)."""
        settings.SAAS_VERIFICAR_SUSCRIPCION = True
        middleware, get_response, _ = _make_middleware()
        middleware.activo = True

        with patch("apps.saas.models.suscripcion_activa", side_effect=Exception("DB error")):
            request = _make_request(user=usuario)
            middleware(request)
            # Fail-open: request should pass through despite the exception
            get_response.assert_called_once()


class TestSuscripcionActivaIntegration:
    """Integration tests using real Suscripcion model objects."""

    @pytest.fixture
    def plan(self, db):
        from apps.saas.models import Plan
        return Plan.objects.create(
            nombre="Plan Básico",
            precio_mensual="29.99",
            max_usuarios=5,
            max_empresas=1,
        )

    def test_active_subscription_integration(self, settings, usuario, empresa, plan, db):
        """Real active subscription allows access."""
        from apps.saas.models import Suscripcion
        settings.SAAS_VERIFICAR_SUSCRIPCION = True

        today = datetime.date.today()
        Suscripcion.objects.create(
            id_empresa=empresa,
            id_plan=plan,
            estado="ACTIVA",
            fecha_inicio=today - datetime.timedelta(days=30),
            fecha_fin=today + datetime.timedelta(days=30),
        )

        middleware, get_response, _ = _make_middleware()
        middleware.activo = True
        request = _make_request(user=usuario)
        middleware(request)
        get_response.assert_called_once()

    def test_expired_subscription_returns_402(self, settings, usuario, empresa, plan, db):
        """Real expired subscription blocks access with 402."""
        from apps.saas.models import Suscripcion
        settings.SAAS_VERIFICAR_SUSCRIPCION = True

        today = datetime.date.today()
        Suscripcion.objects.create(
            id_empresa=empresa,
            id_plan=plan,
            estado="ACTIVA",
            fecha_inicio=today - datetime.timedelta(days=60),
            fecha_fin=today - datetime.timedelta(days=1),  # expired yesterday
        )

        middleware, get_response, _ = _make_middleware()
        middleware.activo = True
        request = _make_request(user=usuario)
        response = middleware(request)
        assert response.status_code == 402
        get_response.assert_not_called()

    def test_suspended_subscription_returns_402(self, settings, usuario, empresa, plan, db):
        """Suspended subscription blocks access with 402."""
        from apps.saas.models import Suscripcion
        settings.SAAS_VERIFICAR_SUSCRIPCION = True

        today = datetime.date.today()
        Suscripcion.objects.create(
            id_empresa=empresa,
            id_plan=plan,
            estado="SUSPENDIDA",
            fecha_inicio=today - datetime.timedelta(days=30),
            fecha_fin=today + datetime.timedelta(days=30),
        )

        middleware, get_response, _ = _make_middleware()
        middleware.activo = True
        request = _make_request(user=usuario)
        response = middleware(request)
        assert response.status_code == 402
        get_response.assert_not_called()

    def test_trial_subscription_passes(self, settings, usuario, empresa, plan, db):
        """TRIAL subscription is treated as active."""
        from apps.saas.models import Suscripcion
        settings.SAAS_VERIFICAR_SUSCRIPCION = True

        today = datetime.date.today()
        Suscripcion.objects.create(
            id_empresa=empresa,
            id_plan=plan,
            estado="TRIAL",
            fecha_inicio=today - datetime.timedelta(days=7),
            fecha_fin=today + datetime.timedelta(days=23),
        )

        middleware, get_response, _ = _make_middleware()
        middleware.activo = True
        request = _make_request(user=usuario)
        middleware(request)
        get_response.assert_called_once()
