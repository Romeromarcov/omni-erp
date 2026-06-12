"""P2-5 (plan 05 hardening) — Content-Security-Policy emitida por Django.

La política global (``CONTENT_SECURITY_POLICY`` en ``settings_base``) es
estricta: ``'self'`` para todo, sin ``'unsafe-inline'`` global. Las vistas de
docs (drf-yasg, solo DEBUG) llevan su relajación mínima POR VISTA vía
``docs_csp_update`` (config/urls.py); aquí se verifica que esa relajación
existe y que NO se filtra a la política global.
"""

import pytest
from csp.middleware import CSPMiddleware
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory

from config.urls import docs_csp_update

HEADER = "Content-Security-Policy"


def _directivas(header_value: str) -> dict[str, str]:
    """Parsea el header en {directiva: "directiva valores..."}."""
    out = {}
    for segmento in header_value.split(";"):
        segmento = segmento.strip()
        if segmento:
            out[segmento.split(" ")[0]] = segmento
    return out


@pytest.mark.unit
def test_middleware_csp_activo_despues_de_whitenoise():
    """El header lo emite Django (no solo nginx) y los estáticos de WhiteNoise
    quedan fuera a propósito (no son documentos)."""
    middleware = settings.MIDDLEWARE
    assert "csp.middleware.CSPMiddleware" in middleware
    assert middleware.index("csp.middleware.CSPMiddleware") > middleware.index(
        "whitenoise.middleware.WhiteNoiseMiddleware"
    )


@pytest.mark.django_db
def test_admin_sigue_respondiendo_y_emite_csp(client):
    """El admin (HTML real del backend) responde 200 con la política estricta."""
    response = client.get("/admin/login/")
    assert response.status_code == 200
    directivas = _directivas(response.headers[HEADER])
    assert directivas["default-src"] == "default-src 'self'"
    assert directivas["script-src"] == "script-src 'self'"
    assert directivas["style-src"] == "style-src 'self'"
    assert directivas["img-src"] == "img-src 'self'"
    assert directivas["font-src"] == "font-src 'self'"
    assert directivas["connect-src"] == "connect-src 'self'"
    assert directivas["object-src"] == "object-src 'none'"
    assert directivas["base-uri"] == "base-uri 'self'"
    assert directivas["form-action"] == "form-action 'self'"
    # Alineada con X_FRAME_OPTIONS=DENY y la CSP de nginx.
    assert directivas["frame-ancestors"] == "frame-ancestors 'none'"


@pytest.mark.django_db
def test_politica_global_sin_unsafe_inline_ni_nonce_suelto(client):
    """Nada de 'unsafe-inline' global (la relajación de docs es por vista) y
    sin nonce: el admin 5.2 no tiene inline ejecutable que autorizar."""
    header = client.get("/admin/login/").headers[HEADER]
    assert "'unsafe-inline'" not in header
    assert "nonce-" not in header
    assert "worker-src" not in header  # solo lo agregan las vistas de docs


@pytest.mark.django_db
def test_api_json_tambien_emite_csp(client):
    """Defensa en profundidad: las respuestas de API llevan el header (cubre
    cualquier render HTML accidental, p. ej. páginas de error)."""
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers[HEADER]


@pytest.mark.unit
def test_docs_relajan_solo_estilos_imagenes_y_worker():
    """``docs_csp_update`` (aplicado a swagger/redoc, solo DEBUG) suma lo
    mínimo que drf-yasg necesita en runtime, sin tocar script-src."""

    @docs_csp_update
    def vista_docs(request):
        return HttpResponse("docs")

    middleware = CSPMiddleware(vista_docs)
    response = middleware(RequestFactory().get("/api/docs/"))
    directivas = _directivas(response[HEADER])

    # Relajaciones mínimas, sumadas a la base 'self'.
    assert directivas["style-src"] == "style-src 'self' 'unsafe-inline'"
    assert directivas["img-src"] == "img-src 'self' data:"
    assert directivas["worker-src"] == "worker-src 'self' blob:"
    # Lo crítico NO se relaja: scripts solo del propio origen.
    assert directivas["script-src"] == "script-src 'self'"
    assert directivas["default-src"] == "default-src 'self'"
    assert directivas["object-src"] == "object-src 'none'"


@pytest.mark.unit
def test_vista_sin_decorador_no_hereda_la_relajacion():
    """La relajación vive en el decorador, no en la política global."""

    def vista_normal(request):
        return HttpResponse("api")

    middleware = CSPMiddleware(vista_normal)
    response = middleware(RequestFactory().get("/api/core/"))
    directivas = _directivas(response[HEADER])
    assert directivas["style-src"] == "style-src 'self'"
    assert "worker-src" not in directivas
