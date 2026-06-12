"""CORS de shells nativos en producción (Plan B apps multiplataforma / ADR-008).

``settings_prod`` debe permitir los orígenes de los empaquetados nativos:

- ``app://omni`` — Electron escritorio (scheme propio; ver ``frontend/electron/main.cjs``).
  El shell NUNCA se sirve desde ``file://`` porque su ``Origin: null`` lo comparten
  los iframes sandboxeados de cualquier web → permitir "null" sería una puerta CSRF.
- ``https://localhost`` — Capacitor Android (``androidScheme: 'https'``).
- ``capacitor://localhost`` — Capacitor iOS (futuro).

El flag ``CORS_NATIVE_SHELLS`` (default on) permite apagarlos por entorno.

Los tests importan ``config.settings_prod`` como módulo (no via django.conf) en un
entorno simulado de producción; eso ejecuta el código real de armado de CORS sin
tocar la configuración Django activa de la suite (que corre con settings de dev).
"""

import importlib
import sys

import pytest

_PROD_ENV = {
    "DJANGO_ENV": "prod",
    "SECRET_KEY": "test-secret",
    "DJANGO_ALLOWED_HOSTS": "api.test.com",
    "DATABASE_URL": "postgres://u:p@h:5432/db",
    "CORS_ALLOWED_ORIGINS": "https://app.test.com",
}

NATIVE_ORIGINS = ("app://omni", "https://localhost", "capacitor://localhost")


def _cargar_settings_prod(monkeypatch, **extra_env):
    for clave, valor in {**_PROD_ENV, **extra_env}.items():
        monkeypatch.setenv(clave, valor)
    # Import limpio: el módulo lee os.environ a nivel de módulo.
    sys.modules.pop("config.settings_prod", None)
    return importlib.import_module("config.settings_prod")


@pytest.fixture(autouse=True)
def _limpiar_modulo():
    yield
    # No dejar el módulo prod cacheado con el entorno simulado.
    sys.modules.pop("config.settings_prod", None)


def test_origenes_nativos_presentes_por_defecto(monkeypatch):
    sp = _cargar_settings_prod(monkeypatch)
    for origen in NATIVE_ORIGINS:
        assert origen in sp.CORS_ALLOWED_ORIGINS, origen
    # Los configurados por entorno siguen presentes y no hay allow-all.
    assert "https://app.test.com" in sp.CORS_ALLOWED_ORIGINS
    assert sp.CORS_ALLOW_ALL_ORIGINS is False


def test_flag_apaga_origenes_nativos(monkeypatch):
    sp = _cargar_settings_prod(monkeypatch, CORS_NATIVE_SHELLS="False")
    for origen in NATIVE_ORIGINS:
        assert origen not in sp.CORS_ALLOWED_ORIGINS, origen


def test_origen_null_jamas_permitido(monkeypatch):
    """El origen "null" (file://, iframes sandboxeados) no debe permitirse nunca."""
    sp = _cargar_settings_prod(monkeypatch)
    assert "null" not in sp.CORS_ALLOWED_ORIGINS


def test_sin_duplicados_si_ya_estan_en_el_entorno(monkeypatch):
    sp = _cargar_settings_prod(
        monkeypatch, CORS_ALLOWED_ORIGINS="https://app.test.com,app://omni"
    )
    assert sp.CORS_ALLOWED_ORIGINS.count("app://omni") == 1
