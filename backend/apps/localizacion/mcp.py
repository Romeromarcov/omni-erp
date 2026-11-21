"""Herramientas MCP del framework de localización (PR-25 / ADR-007).

Herramientas expuestas:
  - ``localizacion_estado_empresa`` (scope ``localizacion:read``)
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from apps.localizacion.services import resumen_localizacion

logger = logging.getLogger("omni.mcp.localizacion")

_SCOPE = "localizacion"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def _parse_uuid_mcp(raw: str, campo: str) -> uuid.UUID:
    if "\x00" in raw:
        raise ValueError(f"El parámetro '{campo}' contiene caracteres inválidos.")
    limpio = raw.strip()
    if not limpio:
        raise ValueError(f"El parámetro '{campo}' no es un UUID válido.")
    try:
        return uuid.UUID(limpio)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"El parámetro '{campo}' no es un UUID válido.") from exc


def localizacion_estado_empresa(
    capability_token: str,
    empresa_id: str | None = None,
) -> dict[str, Any]:
    """
    Consulta el estado de localización (legal/mercado) y los 6 puertos resueltos
    para la empresa del token.

    Scope requerido: ``localizacion:read``

    Args:
        capability_token: Token de capacidad con scope ``localizacion:read``.
        empresa_id:       UUID de la empresa (opcional; si se omite usa la del token).

    Returns:
        dict con ``empresa_id``, ``pais_codigo_iso``, ``pais_normalizado``,
        ``localizacion_legal_activa``, ``localizacion_mercado_activa`` y ``puertos``.
    """
    from apps.core.models import Empresa  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read") as ctx:
        if empresa_id is not None and empresa_id != "":
            empresa_uuid = _parse_uuid_mcp(str(empresa_id), "empresa_id")
            if str(empresa_uuid) != ctx["empresa_id"]:
                raise PermissionError("empresa_id no coincide con el tenant del token.")
        else:
            empresa_uuid = uuid.UUID(ctx["empresa_id"])

        empresa = Empresa.objects.filter(pk=empresa_uuid, activo=True).first()
        if empresa is None:
            raise PermissionError("Empresa no encontrada o inactiva.")

        estado = resumen_localizacion(empresa)
        logger.info(
            "localizacion_estado_empresa | actor=%s | tenant=%s | pais=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            estado["pais_normalizado"],
        )
        return {
            "empresa_id": str(empresa.pk),
            **estado,
        }


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": localizacion_estado_empresa,
        "name": "localizacion_estado_empresa",
        "scope": f"{_SCOPE}:read",
    },
]
