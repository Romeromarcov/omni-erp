"""Herramientas MCP para sincronización offline con concurrencia optimista (CTF-008)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from apps.sync.services import (
    SyncConflictError,
    SyncPushError,
    aplicar_actualizacion_optimista,
)

logger = logging.getLogger("omni.mcp.sync")

_SCOPE = "sync"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def sync_aplicar_actualizacion_optimista(
    capability_token: str,
    entity: str,
    record_id: str,
    expected_fecha_actualizacion: str,
    cambios: dict[str, Any],
    empresa_id: str | None = None,
) -> dict[str, Any]:
    """
    Aplica una edición optimista sobre una entidad sincronizable whitelistada.

    Scope requerido: ``sync:write``

    Ante conflicto de versión (``expected_fecha_actualizacion`` distinto), no
    sobrescribe los cambios recientes y retorna ``ok=False`` con
    ``codigo="CONFLICTO_VERSION"`` y ``registro_servidor``.
    """
    from apps.core.models import Empresa  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:write") as ctx:
        if empresa_id is not None and str(empresa_id).strip():
            try:
                empresa_uuid = uuid.UUID(str(empresa_id).strip())
            except (ValueError, TypeError) as exc:
                raise ValueError("empresa_id no es un UUID válido.") from exc
            if str(empresa_uuid) != ctx["empresa_id"]:
                raise PermissionError("empresa_id no coincide con el tenant del token.")
        else:
            empresa_uuid = uuid.UUID(ctx["empresa_id"])

        empresas = Empresa.objects.filter(pk=empresa_uuid, activo=True)
        if not empresas.exists():
            raise PermissionError("Empresa no encontrada o inactiva.")

        try:
            resultado = aplicar_actualizacion_optimista(
                empresas=empresas,
                entity=entity,
                record_id=record_id,
                expected_fecha_actualizacion=expected_fecha_actualizacion,
                cambios=cambios,
            )
        except SyncConflictError as exc:
            logger.info(
                "sync_aplicar_actualizacion_optimista conflicto | actor=%s | tenant=%s | entity=%s | id=%s",
                ctx["actor_id"],
                ctx["tenant_id"],
                entity,
                record_id,
            )
            return {
                "ok": False,
                "codigo": exc.codigo,
                "error": str(exc),
                "entity": exc.entity,
                "id": exc.record_id,
                "registro_servidor": exc.registro_servidor,
            }
        except SyncPushError as exc:
            raise ValueError(str(exc)) from exc

        logger.info(
            "sync_aplicar_actualizacion_optimista ok | actor=%s | tenant=%s | entity=%s | id=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            entity,
            record_id,
        )
        return {"ok": True, **resultado}


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": sync_aplicar_actualizacion_optimista,
        "name": "sync_aplicar_actualizacion_optimista",
        "scope": f"{_SCOPE}:write",
    },
]
