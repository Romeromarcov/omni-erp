"""Herramientas MCP del plano de control de bots (R-CODE-7 / ADR-003).

Permite a agentes internos o externos autorizados consultar la salud de la flota
de bots de la empresa y pausar/reanudar un bot dejando trazabilidad en ``BotBitacora``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("omni.mcp.bots_ingest")

_SCOPE = "bots"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def _empresa_activa(empresa_id: str):
    from apps.core.models import Empresa  # noqa: PLC0415

    empresa = Empresa.objects.filter(id_empresa=empresa_id, activo=True).first()
    if empresa is None:
        raise PermissionError("Empresa inactiva o no encontrada.")
    return empresa


def bots_estado_flota(capability_token: str, empresa_id: str) -> dict[str, Any]:
    """Devuelve el estado de la flota de bots y la salud de destinos de una empresa.

    Scope requerido: ``bots:read``
    """
    from apps.bots_ingest.services import control  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        empresa = _empresa_activa(ctx["empresa_id"])
        logger.info("bots_estado_flota | actor=%s | tenant=%s", ctx["actor_id"], ctx["tenant_id"])
        return {
            "bots": control.listar_bots(empresa),
            "destinos": control.resumen_destinos(empresa),
        }


def bots_cambiar_habilitado(
    capability_token: str,
    empresa_id: str,
    codigo_bot: str,
    habilitado: bool,
    mensaje: str | None = None,
) -> dict[str, Any]:
    """Pausa o reanuda un bot de la empresa dejando registro en ``BotBitacora``.

    Scope requerido: ``bots:write``
    """
    from apps.bots_ingest.services import control  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_id) as ctx:
        empresa = _empresa_activa(ctx["empresa_id"])
        cambios: dict[str, Any] = {"habilitado": bool(habilitado)}
        if mensaje is not None:
            cambios["mensaje"] = mensaje
        detalle = control.actualizar_bot(
            empresa=empresa,
            codigo=codigo_bot,
            cambios=cambios,
            actor=ctx["actor_id"],
        )
        logger.info(
            "bots_cambiar_habilitado | actor=%s | tenant=%s | bot=%s | habilitado=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            codigo_bot,
            habilitado,
        )
        return detalle


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": bots_estado_flota,
        "name": "bots_estado_flota",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": bots_cambiar_habilitado,
        "name": "bots_cambiar_habilitado",
        "scope": f"{_SCOPE}:write",
    },
]
