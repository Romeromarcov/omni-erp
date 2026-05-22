"""
apps/inventario/mcp.py — Herramientas MCP del módulo de Inventario (ADR-003).

Herramientas expuestas:
  inventario_get_productos     — lista productos de una empresa
  inventario_get_stock_resumen — resumen de stock por almacén
  inventario_get_alertas_stock — productos con stock bajo el punto de reorden
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("omni.mcp.inventario")

_SCOPE = "inventario"


def _ctx(capability_token: str, scope: str) -> dict[str, Any]:
    from apps.core.mcp_server import _require_scope, _resolve_token  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, scope)
    assert context is not None  # noqa: S101
    return context


def inventario_get_productos(
    capability_token: str,
    empresa_id: str,
    buscar: str = "",
    activos_solo: bool = True,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Lista productos de una empresa, con filtro opcional por nombre/SKU.

    Scope requerido: ``inventario:read``

    Args:
        capability_token: Token con scope ``inventario:read``.
        empresa_id:       ID de la empresa.
        buscar:           Texto libre para filtrar por nombre_producto o sku.
        activos_solo:     Si True (default), retorna solo productos activos.
        limit:            Máximo de resultados (default 50, máx 200).

    Returns:
        Lista de productos con id, nombre, sku, precio_venta_sugerido, activo.
    """
    from apps.inventario.models import Producto  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    limit = min(limit, 200)
    qs = Producto.objects.filter(id_empresa=empresa_id)
    if activos_solo:
        qs = qs.filter(activo=True)
    if buscar:
        qs = qs.filter(nombre_producto__icontains=buscar)

    productos = qs.order_by("nombre_producto")[:limit]
    logger.info(
        "inventario_get_productos | actor=%s | tenant=%s | count=%d",
        ctx["actor_id"], ctx["tenant_id"], len(productos),
    )
    return [
        {
            "id_producto": str(p.id_producto),
            "nombre_producto": p.nombre_producto,
            "sku": p.sku or "",
            "precio_venta_sugerido": float(p.precio_venta_sugerido or 0),
            "activo": p.activo,
        }
        for p in productos
    ]


def inventario_get_stock_resumen(
    capability_token: str,
    empresa_id: str,
    almacen_id: str = "",
) -> list[dict[str, Any]]:
    """
    Retorna el stock disponible de todos los productos de una empresa.

    Scope requerido: ``inventario:read``

    Args:
        capability_token: Token con scope ``inventario:read``.
        empresa_id:       ID de la empresa.
        almacen_id:       Filtrar por almacén específico (opcional).

    Returns:
        Lista con producto_id, nombre, almacen, cantidad_disponible,
        cantidad_comprometida, cantidad_disponible_neta.
    """
    from apps.inventario.models import StockActual  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    qs = StockActual.objects.filter(
        id_empresa=empresa_id,
    ).select_related("id_producto", "id_almacen")
    if almacen_id:
        qs = qs.filter(id_almacen=almacen_id)

    logger.info(
        "inventario_get_stock_resumen | actor=%s | tenant=%s | almacen=%s",
        ctx["actor_id"], ctx["tenant_id"], almacen_id or "todos",
    )
    return [
        {
            "producto_id": str(s.id_producto_id),
            "nombre_producto": s.id_producto.nombre_producto,
            "almacen": s.id_almacen.nombre_almacen,
            "cantidad_disponible": float(s.cantidad_disponible),
            "cantidad_comprometida": float(s.cantidad_comprometida),
            "disponible_neto": float(s.cantidad_disponible - s.cantidad_comprometida),
        }
        for s in qs
    ]


def inventario_get_alertas_stock(
    capability_token: str,
    empresa_id: str,
) -> list[dict[str, Any]]:
    """
    Retorna productos cuyo stock disponible cayó por debajo del punto de reorden.

    Scope requerido: ``inventario:read``

    Returns:
        Lista de productos con stock bajo, incluyendo stock_actual y punto_reorden.
    """
    from apps.inventario.models import Producto, StockActual  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    alertas = []
    stocks = (
        StockActual.objects.filter(id_empresa=empresa_id)
        .select_related("id_producto")
        .filter(id_producto__punto_reorden__isnull=False)
    )

    for s in stocks:
        prod = s.id_producto
        if prod.punto_reorden and s.cantidad_disponible <= prod.punto_reorden:
            alertas.append({
                "producto_id": str(prod.id_producto),
                "nombre": prod.nombre_producto,
                "sku": prod.sku or "",
                "stock_actual": float(s.cantidad_disponible),
                "punto_reorden": float(prod.punto_reorden),
                "deficit": float(prod.punto_reorden - s.cantidad_disponible),
            })

    logger.info(
        "inventario_get_alertas_stock | actor=%s | tenant=%s | alertas=%d",
        ctx["actor_id"], ctx["tenant_id"], len(alertas),
    )
    return alertas


# ─────────────────────────────────────────────────────────────────────────────
# Auto-discovery
# ─────────────────────────────────────────────────────────────────────────────

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": inventario_get_productos,
        "name": "inventario_get_productos",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": inventario_get_stock_resumen,
        "name": "inventario_get_stock_resumen",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": inventario_get_alertas_stock,
        "name": "inventario_get_alertas_stock",
        "scope": f"{_SCOPE}:read",
    },
]
