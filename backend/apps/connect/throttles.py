"""Throttles específicos para los endpoints públicos de Omni Connect."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle


class _ConnectScopedThrottle(ScopedRateThrottle):
    """ScopedRateThrottle con resolución dinámica de tasa desde settings."""

    scope: str = ""

    def get_rate(self) -> str | None:
        if not getattr(self, "scope", None):
            return None
        rates = getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_THROTTLE_RATES")
        if isinstance(rates, dict) and self.scope in rates:
            return str(rates[self.scope])
        try:
            rate = api_settings.DEFAULT_THROTTLE_RATES[self.scope]
        except KeyError as exc:
            raise ImproperlyConfigured(f"Falta la tasa '{self.scope}' en DEFAULT_THROTTLE_RATES.") from exc
        return str(rate) if rate is not None else None

    def allow_request(self, request, view) -> bool:
        self.scope = getattr(view, self.scope_attr, None) or type(self).scope
        if not self.scope:
            return True
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super(ScopedRateThrottle, self).allow_request(request, view)


class ConnectPublicoThrottle(_ConnectScopedThrottle):
    """Rate-limit por IP para consultas públicas de perfil y descarga vCard."""

    scope = "connect_publico"


class ConnectLeadThrottle(_ConnectScopedThrottle):
    """Rate-limit por IP para captura pública de leads."""

    scope = "connect_lead"
