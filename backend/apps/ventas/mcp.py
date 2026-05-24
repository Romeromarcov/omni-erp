"""
apps/ventas/mcp.py — Herramientas MCP del módulo de Ventas (ADR-003).

Este módulo define las herramientas MCP propias del dominio de ventas.
Son descubiertas automáticamente por apps/core/mcp_server.py a través del
patrón de auto-discovery: cualquier módulo ``apps.<modulo>.mcp`` que exporte
``MCP_TOOLS = [...]`` queda registrado en el servidor.

Herramientas expuestas:
  ventas_get_cotizacion   — recupera una cotización por ID
  ventas_get_notas_venta  — lista notas de venta de una empresa
  ventas_get_facturas     — lista facturas fiscales de una empresa
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("omni.mcp.ventas")

# Scope prefix para este módulo
_SCOPE = "ventas"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(capability_token: str, scope: str) -> dict:
    """Resuelve y valida token + scope. Lanza PermissionError si falla."""
    from apps.core.mcp_server import _require_scope, _resolve_token  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, scope)
    assert context is not None  # noqa: S101
    return context


# ─────────────────────────────────────────────────────────────────────────────
# Herramientas MCP
# ─────────────────────────────────────────────────────────────────────────────


def ventas_get_cotizacion(
    capability_token: str,
    empresa_id: str,
    cotizacion_id: str,
) -> dict:
    """
    Recupera los detalles de una cotización específica.

    Scope requerido: ``ventas:read``

    Args:
        capability_token: Token con scope ``ventas:read``.
        empresa_id:       ID de la empresa (tenant).
        cotizacion_id:    UUID de la cotización.

    Returns:
        dict con id_cotizacion, numero, cliente, estado, total, detalles.
    """
    from apps.ventas.models import Cotizacion  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    try:
        cot = Cotizacion.objects.prefetch_related("detalles__id_producto").get(
            pk=cotizacion_id,
            id_empresa=empresa_id,
        )
    except Cotizacion.DoesNotExist:
        return {"error": f"Cotización {cotizacion_id} no encontrada."}

    logger.info(
        "ventas_get_cotizacion | actor=%s | tenant=%s | cotizacion=%s",
        ctx["actor_id"], ctx["tenant_id"], cotizacion_id,
    )

    return {
        "id_cotizacion": str(cot.id_cotizacion),
        "numero": cot.numero_cotizacion,
        "cliente": cot.id_cliente.razon_social,
        "estado": cot.estado,
        "fecha": str(cot.fecha_cotizacion),
        "detalles": [
            {
                "producto": d.id_producto.nombre_producto,
                "cantidad": float(d.cantidad),
                "precio_unitario": float(d.precio_unitario),
                "subtotal": float(d.subtotal),
            }
            for d in cot.detalles.all()
        ],
    }


def ventas_get_notas_venta(
    capability_token: str,
    empresa_id: str,
    estado: str = "",
    limit: int = 20,
) -> list:
    """
    Lista notas de venta de una empresa.

    Scope requerido: ``ventas:read``

    Args:
        capability_token: Token con scope ``ventas:read``.
        empresa_id:       ID de la empresa.
        estado:           Filtrar por estado (BORRADOR, ENTREGADA, ANULADA). Vacío = todos.
        limit:            Máximo de resultados (default 20, máx 100).

    Returns:
        Lista de notas con id, numero, cliente, estado, fecha.
    """
    from apps.ventas.models import NotaVenta  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    limit = min(limit, 100)
    qs = NotaVenta.objects.filter(id_empresa=empresa_id).select_related("id_cliente")
    if estado:
        qs = qs.filter(estado=estado)

    notas = qs.order_by("-fecha_nota")[:limit]
    logger.info(
        "ventas_get_notas_venta | actor=%s | tenant=%s | count=%d",
        ctx["actor_id"], ctx["tenant_id"], len(notas),
    )
    return [
        {
            "id_nota_venta": str(n.id_nota_venta),
            "numero": n.numero_nota,
            "cliente": n.id_cliente.razon_social,
            "estado": n.estado,
            "fecha": str(n.fecha_nota),
        }
        for n in notas
    ]


def ventas_get_facturas(
    capability_token: str,
    empresa_id: str,
    estado: str = "",
    limit: int = 20,
) -> list:
    """
    Lista facturas fiscales de una empresa.

    Scope requerido: ``ventas:read``

    Args:
        capability_token: Token con scope ``ventas:read``.
        empresa_id:       ID de la empresa.
        estado:           Filtrar por estado (EMITIDA, ANULADA). Vacío = todas.
        limit:            Máximo de resultados (default 20, máx 100).

    Returns:
        Lista de facturas con id, numero, numero_control, cliente, estado, total.
    """
    from apps.ventas.models import FacturaFiscal  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    limit = min(limit, 100)
    qs = FacturaFiscal.objects.filter(id_empresa=empresa_id).select_related("id_cliente")
    if estado:
        qs = qs.filter(estado=estado)

    facturas = qs.order_by("-fecha_factura")[:limit]
    logger.info(
        "ventas_get_facturas | actor=%s | tenant=%s | count=%d",
        ctx["actor_id"], ctx["tenant_id"], len(facturas),
    )
    return [
        {
            "id_factura": str(f.id_factura),
            "numero_factura": f.numero_factura,
            "numero_control": f.numero_control,
            "cliente": f.id_cliente.razon_social,
            "estado": f.estado,
            "fecha": str(f.fecha_factura),
            "total": float(f.total),
        }
        for f in facturas
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Auto-discovery — exportar lista de herramientas
# ─────────────────────────────────────────────────────────────────────────────

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "fn": ventas_get_cotizacion,
        "name": "ventas_get_cotizacion",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": ventas_get_notas_venta,
        "name": "ventas_get_notas_venta",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": ventas_get_facturas,
        "name": "ventas_get_facturas",
        "scope": f"{_SCOPE}:read",
    },
]
