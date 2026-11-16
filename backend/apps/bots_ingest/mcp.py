"""Herramientas MCP del plano de control de bots (R-CODE-7 / ADR-003).

Permite a agentes internos o externos autorizados consultar la salud de la flota
de bots de la empresa y pausar/reanudar un bot dejando trazabilidad en ``BotBitacora``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("omni.mcp.bots_ingest")

_SCOPE = "bots"


def _ctx(capability_token: str, scope: str) -> dict[str, Any]:
    from apps.core.mcp_server import _require_scope, _resolve_token  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, scope)
    assert context is not None  # nosec B101
    return context


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

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if str(empresa_id) != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")
    empresa = _empresa_activa(ctx["empresa_id"])
    logger.info(
        "bots_estado_flota | actor=%s | tenant=%s", ctx["actor_id"], ctx["tenant_id"]
    )
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

    ctx = _ctx(capability_token, f"{_SCOPE}:write")
    if str(empresa_id) != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")
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
