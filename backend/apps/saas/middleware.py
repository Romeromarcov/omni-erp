"""
M10-T5: Middleware de verificación de suscripción SaaS.

SuscripcionActivaMiddleware:
  Verifica que la empresa del usuario autenticado tenga una suscripción vigente.
  Si no la tiene, retorna HTTP 402 Payment Required.

Configuración en settings:
  MIDDLEWARE = [
      ...
      "apps.saas.middleware.SuscripcionActivaMiddleware",
  ]

  # Rutas excluidas de verificación (siempre pasan):
  SAAS_RUTAS_EXCLUIDAS = ["/api/auth/", "/admin/", "/swagger/", "/api/saas/"]
"""

from __future__ import annotations

import json
import logging

from django.http import HttpResponse

logger = logging.getLogger("omni.saas.middleware")

# Rutas que siempre pasan sin verificar suscripción
RUTAS_EXCLUIDAS_DEFAULT = [
    "/admin/",
    "/api/auth/",
    "/api/token/",
    "/api/saas/",
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
      - El usuario está autenticado
      - La ruta no está en RUTAS_EXCLUIDAS
      - La empresa del usuario no tiene suscripción activa

    No actúa sobre:
      - Usuarios anónimos
      - Rutas excluidas
      - Empresas sin campo 'suscripciones' (compatibilidad)
    """

    def __init__(self, get_response):
        self.get_response = get_response

        from django.conf import settings
        self.rutas_excluidas = getattr(
            settings, "SAAS_RUTAS_EXCLUIDAS", RUTAS_EXCLUIDAS_DEFAULT
        )
        self.activo = getattr(settings, "SAAS_VERIFICAR_SUSCRIPCION", False)

    def __call__(self, request):
        if self.activo and self._debe_verificar(request):
            respuesta_error = self._verificar_suscripcion(request)
            if respuesta_error:
                return respuesta_error

        return self.get_response(request)

    def _debe_verificar(self, request) -> bool:
        """Determina si esta request debe ser verificada."""
        if not request.user or not request.user.is_authenticated:
            return False
        ruta = request.path_info
        return not any(ruta.startswith(excluida) for excluida in self.rutas_excluidas)

    def _verificar_suscripcion(self, request) -> HttpResponse | None:
        """
        Verifica la suscripción. Retorna None si OK, o HttpResponse 402 si falla.
        """
        try:
            from apps.saas.models import suscripcion_activa

            user = request.user
            empresa = user.empresas.first() if hasattr(user, "empresas") else None
            if empresa is None:
                return None  # usuario sin empresa → no verificar

            sus = suscripcion_activa(empresa)
            if sus is None:
                logger.warning(
                    "saas_middleware | empresa=%s | user=%s | sin suscripcion activa",
                    empresa.pk, user.pk,
                )
                return HttpResponse(
                    content=json.dumps({
                        "detail": "Su empresa no tiene una suscripción activa. "
                                  "Por favor, contáctenos para activar su plan.",
                        "codigo": "SUSCRIPCION_REQUERIDA",
                    }),
                    content_type="application/json",
                    status=402,
                )
        except Exception as exc:
            logger.error("saas_middleware ERROR: %s", exc)
            # En caso de error interno, permitir el paso (fail-open)
        return None
