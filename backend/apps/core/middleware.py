"""Middleware de contexto RLS (P0-1 del plan de hardening).

Fija, por request HTTP autenticado, el conjunto de empresas visibles y el flag
de bypass en la conexión PostgreSQL, de modo que las políticas Row Level
Security filtren a nivel de base de datos. Ver ``apps/core/rls.py``.

La autenticación de la API es JWT (DRF la resuelve en la vista, no en
``AuthenticationMiddleware``), por lo que este middleware resuelve el usuario
del token por su cuenta para no depender del tipo de endpoint.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed

from . import rls

logger = logging.getLogger("apps")


class RLSContextMiddleware:
    """Aplica el contexto RLS según el usuario autenticado del request."""

    def __init__(self, get_response):
        self.get_response = get_response
        if not getattr(settings, "RLS_ENABLED", False):
            # Sin RLS activo el middleware se descarta limpiamente; el signal
            # de default sigue garantizando conexiones consistentes.
            raise MiddlewareNotUsed()

    def __call__(self, request):
        self._apply_context(request)
        try:
            return self.get_response(request)
        finally:
            # Restaura el default de conexión (bypass on) por si en el futuro
            # se habilita reutilización de conexiones / pooling.
            rls.apply_system_default()

    def _apply_context(self, request) -> None:
        user = self._resolve_user(request)
        if user is None or not getattr(user, "is_authenticated", False):
            # Anónimo => fail-closed (sin empresas, sin bypass).
            rls.apply_context([], bypass=False)
            return
        if getattr(user, "es_superusuario_omni", False):
            rls.apply_context([], bypass=True)
            return
        from .viewsets import get_empresas_visible

        empresa_ids = list(
            get_empresas_visible(user).values_list("id_empresa", flat=True)
        )
        rls.apply_context(empresa_ids, bypass=False)

    @staticmethod
    def _resolve_user(request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user
        # Resolver vía JWT (la API no usa sesión).
        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication

            result = JWTAuthentication().authenticate(request)
        except Exception:
            # Token inválido/ausente => tratado como anónimo (fail-closed).
            return None
        if result is not None:
            return result[0]
        return None
