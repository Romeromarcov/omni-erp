"""Fase 1 (seguridad) — guard SSRF de webhooks de personalización (B310).

Verifica que `_validar_url_externa` bloquea esquemas peligrosos y destinos
internos (loopback, privados, link-local) para que un webhook configurado por un
tenant no pueda leer archivos locales ni alcanzar servicios internos.
"""
import pytest

from apps.personalizacion.dsl import _validar_url_externa


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://evil.example.com/x",
        "gopher://127.0.0.1:6379/_",
        "http://127.0.0.1:8000/admin",       # loopback
        "http://localhost/internal",          # loopback por nombre
        "http://169.254.169.254/latest/meta-data/",  # metadata de nube (link-local)
        "http://10.0.0.5/secret",             # privada
        "http://192.168.1.1/router",          # privada
        "http://[::1]/x",                     # loopback IPv6
        "https://nohaytld/sinhost",           # host no resoluble
    ],
)
def test_bloquea_destinos_peligrosos(url):
    with pytest.raises(ValueError):
        _validar_url_externa(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://93.184.216.34/ok",   # IP pública literal (sin depender de DNS)
        "https://8.8.8.8/webhook",   # IP pública literal
    ],
)
def test_permite_destinos_publicos(url):
    # No debe lanzar para http/https hacia IPs públicas (usamos literales para que
    # el test sea determinístico también sin resolución DNS).
    _validar_url_externa(url)
