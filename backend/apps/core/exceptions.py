"""Helpers centralizados para saneamiento de respuestas de error HTTP y MCP (R-CODE-8)."""

from __future__ import annotations

import logging
import re
from typing import Any

from rest_framework.response import Response

_logger = logging.getLogger(__name__)


class DomainError(Exception):
    """Excepción base opcional para errores de dominio controlados."""


CONTROLLED_DOMAIN_ERROR_TYPES: tuple[type[BaseException], ...] = (DomainError,)

_UNSAFE_TRACE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
    re.compile(r"\bDETAIL:\s"),
    re.compile(r"\bCONTEXT:\s"),
    re.compile(r'\bFile "[^"\n]+", line \d+'),
    re.compile(r"\b(?:SELECT|DELETE)\b[^\n;]{0,200}\bFROM\b", re.IGNORECASE),
    re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\b[^\n;]{0,120}\bSET\b", re.IGNORECASE),
    re.compile(r"\b(?:password|passwd|secret|api_key|access_token)\s*=", re.IGNORECASE),
)


def is_controlled_domain_error(
    exc: BaseException,
    extra_types: tuple[type[BaseException], ...] = (),
) -> bool:
    """Indica si ``exc`` pertenece a una jerarquía de error de dominio controlada."""
    return isinstance(exc, CONTROLLED_DOMAIN_ERROR_TYPES + extra_types)


def _extract_safe_message(exc: Exception, *, default_message: str) -> str:
    """Normaliza ``str(exc)`` y descarta mensajes vacíos o con trazas técnicas/SQL."""
    message = str(exc).strip()
    if not message:
        return default_message
    if any(pattern.search(message) for pattern in _UNSAFE_TRACE_PATTERNS):
        _logger.warning(
            "Mensaje de excepción controlada descartado por patrón técnico (%s).",
            type(exc).__name__,
        )
        return default_message
    return message


def domain_error_response(
    exc: Exception,
    *,
    status_code: int = 400,
    key: str = "error",
    extra: dict[str, Any] | None = None,
    default_message: str = "No se pudo completar la operación.",
) -> Response:
    """Construye una respuesta HTTP para un error de dominio controlado."""
    msg = _extract_safe_message(exc, default_message=default_message)
    payload: dict[str, Any] = {key: msg}
    if extra:
        payload.update({k: v for k, v in extra.items() if k != key})
    return Response(payload, status=status_code)


def unexpected_error_response(
    exc: Exception,
    *,
    logger: logging.Logger,
    context: str,
    status_code: int = 500,
    key: str = "error",
    public_message: str = "Error interno al procesar la solicitud.",
) -> Response:
    """Registra el error inesperado en el log y responde con un mensaje público genérico."""
    logger.exception("Error inesperado en %s", context)
    return Response({key: public_message}, status=status_code)


def sanitize_mcp_error(
    exc: Exception,
    *,
    logger: logging.Logger,
    tool_name: str,
    controlled_types: tuple[type[BaseException], ...] = CONTROLLED_DOMAIN_ERROR_TYPES,
    default_message: str = "No se pudo completar la operación solicitada.",
) -> str:
    """Devuelve un mensaje seguro para herramientas MCP sin exponer fallos internos."""
    if is_controlled_domain_error(exc, controlled_types):
        return _extract_safe_message(exc, default_message=default_message)
    logger.exception("Error inesperado en tool MCP %s", tool_name)
    return default_message
