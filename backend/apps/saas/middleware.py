"""
M10-T5 / Plan C — Fase C2: Middleware de verificación de suscripción SaaS.

SuscripcionActivaMiddleware:
  Verifica que la empresa del usuario autenticado tenga una suscripción vigente.
  Si no la tiene, retorna HTTP 402 Payment Required.

Activación (off por defecto, fail-open):
  SAAS_VERIFICAR_SUSCRIPCION=True  (variable de entorno) — se activa en staging
  antes que en producción para validar el flujo 402 de punta a punta.

  # Rutas excluidas de verificación (siempre pasan):
  SAAS_RUTAS_EXCLUIDAS = ["/api/auth/", "/admin/", "/swagger/", "/api/saas/"]

Nota de diseño (auth JWT): la API se autentica con Bearer JWT, que DRF resuelve
DENTRO de la vista. A nivel de middleware Django, `request.user` es AnonymousUser
para esas requests. Por eso el middleware resuelve el usuario él mismo con
JWTAuthentication, además de respetar la sesión de Django (admin).
"""

from __future__ import annotations

import json
import logging
import uuid

from django.http import HttpResponse

logger = logging.getLogger("omni.saas.middleware")

# Rutas que siempre pasan sin verificar suscripción
RUTAS_EXCLUIDAS_DEFAULT = [
    "/admin/",
    "/api/auth/",
    "/api/token/",
    "/api/saas/",
    "/api/public/",
    "/swagger/",
    "/redoc/",
    "/health/",
    "/static/",
    "/media/",
]


class SuscripcionActivaMiddleware:
    """
    Middleware que verifica que el usuario autenticado tenga una suscripción
    SaaS vigente en su empresa.

    Retorna 402 Payment Required si:
      - El usuario está autenticado (sesión Django o Bearer JWT)
      - NO es superusuario Omni (el proveedor no requiere suscripción)
      - La ruta no está en RUTAS_EXCLUIDAS
      - La empresa del usuario no tiene suscripción activa

    No actúa sobre:
      - Usuarios anónimos / tokens inválidos
      - Rutas excluidas
      - Usuarios sin empresa asignada
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # El flag se lee por request (no en __init__) para poder activarlo en
        # staging sin reiniciar y para que los tests lo puedan sobreescribir.
        from django.conf import settings

        activo = getattr(settings, "SAAS_VERIFICAR_SUSCRIPCION", False)
        if activo and self._ruta_verificable(request):
            respuesta_error = self._verificar_suscripcion(request)
            if respuesta_error:
                return respuesta_error

        return self.get_response(request)

    @staticmethod
    def _ruta_verificable(request) -> bool:
        """True si la ruta NO está excluida (la auth se evalúa después)."""
        from django.conf import settings

        rutas_excluidas = getattr(settings, "SAAS_RUTAS_EXCLUIDAS", RUTAS_EXCLUIDAS_DEFAULT)
        ruta = request.path_info
        return not any(ruta.startswith(excluida) for excluida in rutas_excluidas)

    @staticmethod
    def _resolver_usuario(request):
        """
        Devuelve el usuario autenticado por sesión Django o por Bearer JWT, o
        None si la request es anónima o el token es inválido (en cuyo caso la
        propia vista responderá 401; el middleware no debe enmascararlo con 402).
        """
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return user

        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication

            resultado = JWTAuthentication().authenticate(request)
            if resultado is not None:
                return resultado[0]
        except Exception:
            # Token ausente/ inválido/ expirado → tratar como anónimo (no 402).
            return None
        return None

    @staticmethod
    def _resolver_empresa(request, user):
        """
        Resuelve la empresa activa del usuario respetando ``X-Empresa-ID`` si
        el usuario pertenece a ella. Ante header ajeno o malformado cae en
        ``user.empresas.first()`` (nunca confía en un tenant externo).
        """
        if not hasattr(user, "empresas"):
            return None

        raw_header = None
        headers = getattr(request, "headers", None)
        if headers is not None:
            raw_header = headers.get("X-Empresa-ID")
        if raw_header is None:
            raw_header = getattr(request, "META", {}).get("HTTP_X_EMPRESA_ID")

        if raw_header:
            raw_str = str(raw_header).strip()
            if "\x00" not in raw_str:
                try:
                    empresa_uuid = uuid.UUID(raw_str)
                except (ValueError, TypeError):
                    logger.warning(
                        "saas_middleware | user=%s | X-Empresa-ID inválido, usando fallback",
                        getattr(user, "pk", None),
                    )
                else:
                    empresa_match = user.empresas.filter(pk=empresa_uuid).first()
                    if empresa_match is not None:
                        return empresa_match
                    logger.warning(
                        "saas_middleware | user=%s | X-Empresa-ID ajeno rechazado, usando fallback",
                        getattr(user, "pk", None),
                    )

        return user.empresas.first()

    def _verificar_suscripcion(self, request) -> HttpResponse | None:
        """
        Verifica la suscripción. Retorna None si OK, 402 si no hay plan activo,
        o 503 si ocurre un error interno con SAAS_FAIL_CLOSED=True.
        """
        from django.conf import settings

        try:
            from apps.saas.models import suscripcion_activa

            user = self._resolver_usuario(request)
            if user is None:
                return None  # anónimo → la vista decide (401), no 402

            # El proveedor (dueño del software) no requiere suscripción.
            if getattr(user, "es_superusuario_omni", False):
                return None

            empresa = self._resolver_empresa(request, user)
            if empresa is None:
                return None  # usuario sin empresa → no verificar

            sus = suscripcion_activa(empresa)
            if sus is None:
                logger.warning(
                    "saas_middleware | empresa=%s | user=%s | sin suscripcion activa",
                    empresa.pk,
                    user.pk,
                )
                return HttpResponse(
                    content=json.dumps(
                        {
                            "detail": "Su empresa no tiene una suscripción activa. "
                            "Por favor, contáctenos para activar su plan.",
                            "codigo": "SUSCRIPCION_REQUERIDA",
                        }
                    ),
                    content_type="application/json",
                    status=402,
                )
        except Exception as exc:
            logger.error("saas_middleware ERROR: %s", exc, exc_info=True)
            if getattr(settings, "SAAS_FAIL_CLOSED", False):
                return HttpResponse(
                    content=json.dumps(
                        {
                            "detail": "No se pudo verificar la suscripción en este momento. Intente nuevamente.",
                            "codigo": "SERVICIO_SUSCRIPCION_NO_DISPONIBLE",
                        }
                    ),
                    content_type="application/json",
                    status=503,
                )
            # Política fail-open (default): ante error interno permite paso si SAAS_FAIL_CLOSED=False.
        return None
