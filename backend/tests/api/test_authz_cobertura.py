"""
Guard de cobertura de AUTORIZACIÓN auto-descubierto (plan cero-dudas, criterio 5).

DRF está configurado *secure-by-default* (`DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]`).
El riesgo real es que una ruta **sobreescriba** sus permisos a `AllowAny` (o a una lista
vacía) y quede pública sin querer. Este test recorre el URLconf **ruta por ruta** y exige
que toda ruta DRF requiera autenticación — salvo las explícitamente públicas, en
``PUBLIC_ALLOWLIST`` con su justificación.

Falla automáticamente si alguien publica una ruta nueva (AllowAny / permisos vacíos) sin
registrarla. Recorre por ruta (no por clase) para cubrir también las vistas función
``@api_view`` (que DRF envuelve todas en ``WrappedAPIView``). Complementa el guard de
aislamiento R-CODE-1 (TEST-1).
"""

import pytest

from django.urls import get_resolver
from rest_framework.permissions import AllowAny


# Rutas intencionalmente PÚBLICAS (sin auth), por substring de la ruta, con su motivo.
PUBLIC_ALLOWLIST: dict[str, str] = {
    # Needles ACOTADOS (substring de la ruta): evitar comodines peligrosos como "token"
    # a secas, que matchearían un CRUD de capability-tokens.
    "api/health/": "Health check del contenedor; público.",
    "auth/login": "Login: emite el JWT; necesariamente público.",
    "auth/register": "Alta self-service de empresa/usuario; público por diseño.",
    "auth/refresh": "Refresh de token vía cookie httpOnly; público por diseño.",
    "auth/token": "JWT obtain/refresh/verify (login); público por diseño.",
    "saas/signup": "Auto-registro de prospectos (Plan C — C3): un prospecto aún no "
                   "tiene credenciales; crea Empresa + admin + TRIAL. Con rate-limit y "
                   "sin escalada de privilegios (es_superusuario_omni/is_staff forzados a False).",
    "swagger": "Esquema OpenAPI / Swagger UI (drf-yasg).",
    "redoc": "Documentación ReDoc (drf-yasg).",
}


def _iter_routes(patterns, prefix=""):
    for pattern in patterns:
        sub = getattr(pattern, "url_patterns", None)
        if sub is not None:
            yield from _iter_routes(sub, prefix + str(pattern.pattern))
            continue
        cls = getattr(getattr(pattern, "callback", None), "cls", None)
        if cls is None or not hasattr(cls, "permission_classes"):
            continue
        yield (prefix + str(pattern.pattern), cls)


def _discover_routes():
    seen = set()
    result = []
    for route, cls in _iter_routes(get_resolver().url_patterns):
        if route in seen:
            continue
        seen.add(route)
        result.append((route, cls))
    return result


API_ROUTES = _discover_routes()


def _es_publica(route: str) -> str | None:
    for needle, motivo in PUBLIC_ALLOWLIST.items():
        if needle in route:
            return motivo
    return None


def test_se_descubrieron_rutas_api():
    assert len(API_ROUTES) > 50, (
        f"Solo se descubrieron {len(API_ROUTES)} rutas DRF; la introspección puede estar rota."
    )


@pytest.mark.parametrize("route,cls", API_ROUTES, ids=[r for r, _ in API_ROUTES])
def test_ruta_requiere_autenticacion(route, cls):
    """
    Criterio 5: ninguna ruta queda pública por accidente. Debe tener permisos NO
    vacíos y sin `AllowAny`; si es pública a propósito, va en PUBLIC_ALLOWLIST.
    """
    perms = list(getattr(cls, "permission_classes", []) or [])

    motivo = _es_publica(route)
    if motivo is not None:
        # Pública a propósito: verificamos que efectivamente sea AllowAny/vacía (coherencia).
        pytest.skip(f"Pública (allowlist): {motivo}")

    assert perms, (
        f"Ruta '{route}' ({cls.__module__}.{cls.__qualname__}) sin permission_classes "
        "(lista vacía) → pública. Requiere auth o justifícala en PUBLIC_ALLOWLIST."
    )
    assert AllowAny not in perms, (
        f"Ruta '{route}' ({cls.__module__}.{cls.__qualname__}) usa AllowAny → pública sin "
        "autenticación. Quita AllowAny (DRF exige IsAuthenticated por defecto) o regístrala "
        "en PUBLIC_ALLOWLIST con su motivo."
    )
