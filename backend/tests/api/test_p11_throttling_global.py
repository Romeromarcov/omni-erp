"""
P1-1 Hardening — Throttling global DRF.

Verifica dos cosas:

1. La CONFIGURACIÓN global está activa: REST_FRAMEWORK declara
   DEFAULT_THROTTLE_CLASSES (Anon + User) y DEFAULT_THROTTLE_RATES con las
   claves 'anon', 'user' y 'signup' (esta última preexistente — guardia de
   regresión, ver apps/saas/views.py).

2. El COMPORTAMIENTO de throttling: una vista DRF con AnonRateThrottle /
   UserRateThrottle devuelve 429 al exceder el límite.

Para (2) NO usamos un endpoint real con @override_settings de
DEFAULT_THROTTLE_CLASSES: las vistas DRF enlazan `throttle_classes` en tiempo
de importación, así que un override puede no reflejarse según el orden en que
la suite importa la URLconf (esto causaba fallos solo cuando este archivo
corría DESPUÉS de otros). En su lugar instanciamos una vista de prueba
autocontenida con el throttle adjunto explícitamente y la invocamos vía
APIRequestFactory. El resultado es determinista e independiente del orden.

El conftest hace cache.clear() autouse entre tests; además limpiamos aquí.
"""

import pytest
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from django.contrib.auth import get_user_model


# ── Throttles de prueba con tasa fija (3/min) ─────────────────────────────────


class _AnonThrottle3Min(AnonRateThrottle):
    scope = "anon"
    rate = "3/min"


class _UserThrottle3Min(UserRateThrottle):
    scope = "user"
    rate = "3/min"


class _AnonThrottledView(APIView):
    """Vista pública con AnonRateThrottle a 3/min."""

    permission_classes = []
    authentication_classes = []
    throttle_classes = [_AnonThrottle3Min]

    def get(self, request):
        return Response({"ok": True})


class _UserThrottledView(APIView):
    """Vista autenticada con UserRateThrottle a 3/min."""

    throttle_classes = [_UserThrottle3Min]

    def get(self, request):
        return Response({"ok": True})


@pytest.fixture(autouse=True)
def _limpiar_cache():
    """Limpia la caché de throttling antes y después del test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def usuario(db):
    User = get_user_model()
    return User.objects.create_user(
        username="p11_throttle_user",
        password="p11_Password!",
        email="p11@test.com",
        is_active=True,
    )


# ── Comportamiento: anon throttle ─────────────────────────────────────────────


def test_anon_throttle_devuelve_429_al_exceder_limite(factory):
    """
    Un cliente anónimo recibe 429 al superar el límite (3/min):
    las 3 primeras requests pasan, la 4ta devuelve 429.
    """
    view = _AnonThrottledView.as_view()

    for i in range(3):
        resp = view(factory.get("/_throttle-probe/"))
        assert resp.status_code != 429, (
            f"Request #{i + 1} fue throttled prematuramente (esperaba que pasara)"
        )

    resp = view(factory.get("/_throttle-probe/"))
    assert resp.status_code == 429, (
        f"Se esperaba 429 en la request #4 pero se obtuvo {resp.status_code}"
    )


def test_anon_throttle_primeras_requests_pasan(factory):
    """Las primeras N requests (dentro del límite) no son throttled."""
    view = _AnonThrottledView.as_view()
    for i in range(3):
        resp = view(factory.get("/_throttle-probe/"))
        assert resp.status_code != 429, (
            f"Request #{i + 1} fue bloqueada antes del límite (tasa: 3/min)"
        )


# ── Comportamiento: user throttle ─────────────────────────────────────────────


def test_user_throttle_devuelve_429_al_exceder_limite(factory, usuario):
    """
    Un usuario autenticado recibe 429 al superar el límite (3/min).
    El UserRateThrottle cuenta por usuario; tras 3 requests, la 4ta da 429.
    """
    view = _UserThrottledView.as_view()

    for i in range(3):
        req = factory.get("/_throttle-probe/")
        force_authenticate(req, user=usuario)
        resp = view(req)
        assert resp.status_code != 429, (
            f"Request #{i + 1} fue throttled prematuramente"
        )

    req = factory.get("/_throttle-probe/")
    force_authenticate(req, user=usuario)
    resp = view(req)
    assert resp.status_code == 429, (
        f"Se esperaba 429 en la request #4 pero se obtuvo {resp.status_code}"
    )


# ── Configuración real de producción ──────────────────────────────────────────


def test_configuracion_throttle_global_presente(settings):
    """
    DEFAULT_THROTTLE_CLASSES y DEFAULT_THROTTLE_RATES están en REST_FRAMEWORK
    con las clases Anon/User y las claves 'anon', 'user' y 'signup'.

    La clave 'signup' es preexistente (apps/saas/views.py usa scope 'signup');
    este test es la guardia de regresión para que no vuelva a borrarse.
    """
    rf = settings.REST_FRAMEWORK
    assert "DEFAULT_THROTTLE_CLASSES" in rf, (
        "DEFAULT_THROTTLE_CLASSES no está en REST_FRAMEWORK"
    )
    assert "DEFAULT_THROTTLE_RATES" in rf, (
        "DEFAULT_THROTTLE_RATES no está en REST_FRAMEWORK"
    )

    rates = rf["DEFAULT_THROTTLE_RATES"]
    for clave in ("anon", "user", "signup"):
        assert clave in rates, (
            f"Falta tasa '{clave}' en DEFAULT_THROTTLE_RATES"
        )

    class_names = [c.split(".")[-1] for c in rf["DEFAULT_THROTTLE_CLASSES"]]
    assert "AnonRateThrottle" in class_names, (
        "AnonRateThrottle no está en DEFAULT_THROTTLE_CLASSES"
    )
    assert "UserRateThrottle" in class_names, (
        "UserRateThrottle no está en DEFAULT_THROTTLE_CLASSES"
    )
