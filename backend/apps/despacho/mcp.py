"""
apps/despacho/mcp.py — Herramientas MCP del módulo de Despacho (ADR-003).

Descubiertas por apps/core/mcp_server.py vía el patrón de auto-discovery
(``MCP_TOOLS``). Solo lectura (scope ``despacho:read``): los agentes consultan
los despachos pendientes de entrega; las transiciones de estado quedan para
operadores humanos vía API.

Herramientas expuestas:
  despacho_get_pendientes — lista despachos PENDIENTE/EN_RUTA de una empresa
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger("omni.mcp.despacho")

_SCOPE = "despacho"


def _ctx(capability_token: str, scope: str) -> dict:
    """Resuelve y valida token + scope. Lanza PermissionError si falla."""
    from apps.core.mcp_server import _require_scope, _resolve_token  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, scope)
    assert context is not None  # noqa: S101
    return context


def despacho_get_pendientes(
    capability_token: str,
    empresa_id: str,
    incluir_en_ruta: bool = True,
    limit: int = 20,
) -> list:
    """
    Lista los despachos pendientes de entrega de una empresa.

    Scope requerido: ``despacho:read``

    Args:
        capability_token: Token con scope ``despacho:read``.
        empresa_id:       ID de la empresa (debe coincidir con el tenant del token).
        incluir_en_ruta:  True (default) = PENDIENTE + EN_RUTA; False = solo PENDIENTE.
        limit:            Máximo de resultados (default 20, máx 100).

    Returns:
        Lista de despachos con numero, estado, fecha, cliente, dirección y
        transportista asignado.
    """
    from apps.despacho.models import Despacho  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    estados = [Despacho.ESTADO_PENDIENTE]
    if incluir_en_ruta:
        estados.append(Despacho.ESTADO_EN_RUTA)

    limit = max(1, min(limit, 100))  # clamp: el slice negativo no está soportado
    despachos = (
        Despacho.objects.filter(id_empresa=empresa_id, estado_despacho__in=estados)
        .select_related("id_nota_venta__id_cliente", "id_transportista")
        .order_by("fecha_despacho")[:limit]
    )

    logger.info(
        "despacho_get_pendientes | actor=%s | tenant=%s | count=%d",
        ctx["actor_id"], ctx["tenant_id"], len(despachos),
    )
    return [
        {
            "id_despacho": str(d.id_despacho),
            "numero": d.numero_despacho,
            "estado": d.estado_despacho,
            "fecha_despacho": d.fecha_despacho.isoformat(),
            "fecha_entrega_estimada": (
                d.fecha_entrega_estimada.isoformat() if d.fecha_entrega_estimada else None
            ),
            "nota_venta": d.id_nota_venta.numero_nota if d.id_nota_venta else None,
            "cliente": (
                d.id_nota_venta.id_cliente.razon_social if d.id_nota_venta else None
            ),
            "direccion_entrega": d.direccion_destino,
            "transportista": (
                f"{d.id_transportista.nombre} {d.id_transportista.apellido}"
                if d.id_transportista
                else None
            ),
        }
        for d in despachos
    ]


# ── Auto-discovery — exportar lista de herramientas ──────────────────────────

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "fn": despacho_get_pendientes,
        "name": "despacho_get_pendientes",
        "scope": f"{_SCOPE}:read",
    },
]
