"""Autenticación máquina-a-máquina sobre REST con ``core.CapabilityToken``.

Permite que servicios hermanos (como ``lubrikca-bots``, ADR-011) autentiquen contra
endpoints REST explícitos usando un ``CapabilityToken`` con scopes granulares
(p. ej. ``bots:ingest``, ``bots:heartbeat``, ``tareas:write``), sin depender de
credenciales de usuario ni rotación de cookies ``httpOnly``.

Cabeceras aceptadas (en orden de precedencia):
- ``X-Capability-Token: <uuid>``
- ``X-Bot-Key: <uuid>``
- ``Authorization: CapabilityToken <uuid>``

Seguridad (defensa en profundidad):
- No se agrega a ``DEFAULT_AUTHENTICATION_CLASSES`` global: solo las vistas máquina-a-máquina
  declaran ``CapabilityTokenAuthentication`` y exigen su scope explícito.
- ``RLSContextMiddleware`` reconoce estas cabeceras para acotar ``omni.rls_empresas`` a la
  empresa propietaria del token (fail-closed si el token es inválido, inactivo o expirado).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed

from .models import CapabilityToken


def extract_capability_token(request) -> str | None:
    """Extrae el valor crudo del token desde las cabeceras HTTP soportadas."""
    meta = getattr(request, "META", None) or {}
    for header in ("HTTP_X_CAPABILITY_TOKEN", "HTTP_X_BOT_KEY"):
        raw = meta.get(header)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    auth = meta.get("HTTP_AUTHORIZATION")
    if isinstance(auth, str):
        partes = auth.strip().split(None, 1)
        if len(partes) == 2 and partes[0].lower() == "capabilitytoken" and partes[1].strip():
            return partes[1].strip()
    return None


@dataclass(frozen=True)
class CapabilityPrincipal:
    """Principal autenticado asociado a un ``CapabilityToken`` de una empresa."""

    capability_token: CapabilityToken

    @property
    def pk(self) -> str:
        return f"cap:{self.capability_token.pk}"

    @property
    def id(self):
        return self.capability_token.pk

    @property
    def empresa(self):
        return self.capability_token.empresa

    @property
    def username(self) -> str:
        return f"cap:{str(self.capability_token.token)[:8]}"

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_staff(self) -> bool:
        return False

    @property
    def is_superuser(self) -> bool:
        return False

    @property
    def es_superusuario_omni(self) -> bool:
        return False

    def has_perm(self, perm: str, obj=None) -> bool:
        return False

    def has_perms(self, perm_list, obj=None) -> bool:
        return False

    def has_module_perms(self, app_label: str) -> bool:
        return False

    def has_scope(self, scope: str) -> bool:
        return self.capability_token.has_scope(scope)


def resolve_capability_principal(
    request, *, mark_used: bool = False
) -> tuple[CapabilityPrincipal, CapabilityToken] | None:
    """Valida la cabecera de capacidad si viene presente.

    Retorna ``None`` si la petición no trae cabecera de capacidad; lanza
    ``AuthenticationFailed`` si trae una cabecera inválida, revocada o expirada.
    """
    raw = extract_capability_token(request)
    if raw is None:
        return None
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError) as exc:
        raise AuthenticationFailed("Token de capacidad inválido.") from exc

    token_obj = (
        CapabilityToken.objects.select_related("empresa", "creado_por")
        .filter(token=parsed, activo=True, empresa__activo=True)
        .first()
    )
    if token_obj is None or token_obj.is_expired():
        raise AuthenticationFailed("Token de capacidad inválido o expirado.")

    if mark_used:
        token_obj.mark_used()

    return CapabilityPrincipal(token_obj), token_obj


class CapabilityTokenAuthentication(authentication.BaseAuthentication):
    """Autenticación DRF para endpoints máquina-a-máquina con ``CapabilityToken``."""

    def authenticate(self, request):
        return resolve_capability_principal(request, mark_used=True)

    def authenticate_header(self, request) -> str:
        return "CapabilityToken"


def tiene_scope_capacidad(user, scope: str) -> bool:
    """True si ``user`` es un ``CapabilityPrincipal`` con el ``scope`` requerido."""
    fn = getattr(user, "has_scope", None)
    return bool(callable(fn) and fn(scope))
