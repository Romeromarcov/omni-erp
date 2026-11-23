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

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Dict, List

logger = logging.getLogger("omni.mcp.ventas")

# Scope prefix para este módulo
_SCOPE = "ventas"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    """Resuelve y valida token/scope/tenant abriendo ``rls_tenant_context``."""
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


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

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        try:
            cot = Cotizacion.objects.prefetch_related("detalles__id_producto").get(
                pk=cotizacion_id,
                id_empresa=empresa_id,
            )
        except Cotizacion.DoesNotExist:
            return {"error": f"Cotización {cotizacion_id} no encontrada."}

        logger.info(
            "ventas_get_cotizacion | actor=%s | tenant=%s | cotizacion=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            cotizacion_id,
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
                    # M-BUG-1: monetario como Decimal (no float).
                    "precio_unitario": d.precio_unitario,
                    "subtotal": d.subtotal,
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

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        limit = min(limit, 100)
        qs = NotaVenta.objects.filter(id_empresa=empresa_id).select_related("id_cliente")
        if estado:
            qs = qs.filter(estado=estado)

        notas = qs.order_by("-fecha_nota")[:limit]
        logger.info(
            "ventas_get_notas_venta | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(notas),
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

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        limit = min(limit, 100)
        qs = FacturaFiscal.objects.filter(id_empresa=empresa_id).select_related("id_cliente")
        if estado:
            qs = qs.filter(estado=estado)

        facturas = qs.order_by("-fecha_emision")[:limit]
        logger.info(
            "ventas_get_facturas | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(facturas),
        )
        return [
            {
                "id_factura": str(f.id_factura),
                "numero_factura": f.numero_factura,
                "numero_control": f.numero_control,
                "cliente": f.id_cliente.razon_social,
                "estado": f.estado,
                "fecha": str(f.fecha_emision),
                # M-BUG-1: monetario como Decimal (no float) para no perder precisión.
                "total": f.monto_total,
            }
            for f in facturas
        ]


def ventas_listar_notas_debito_fiscales(
    capability_token: str,
    empresa_id: str,
    estado: str = "",
    limit: int = 20,
) -> list:
    """
    Lista notas de débito fiscales de una empresa.

    Scope requerido: ``ventas:read``
    """
    from apps.ventas.models import NotaDebitoFiscal  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        limit = min(max(int(limit), 1), 100)
        qs = NotaDebitoFiscal.objects.filter(id_empresa=empresa_id, activo=True).select_related(
            "id_cliente", "id_factura_origen"
        )
        if estado:
            qs = qs.filter(estado=str(estado).strip().upper())

        notas = qs.order_by("-fecha_emision", "-fecha_creacion")[:limit]
        logger.info(
            "ventas_listar_notas_debito_fiscales | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(notas),
        )
        return [
            {
                "id_nota_debito_fiscal": str(n.id_nota_debito_fiscal),
                "numero_nota_debito": n.numero_nota_debito,
                "numero_control": n.numero_control,
                "factura_origen": n.id_factura_origen.numero_factura,
                "cliente": n.id_cliente.razon_social,
                "motivo": n.motivo,
                "estado": n.estado,
                "ambito": n.ambito,
                "fecha": str(n.fecha_emision),
                "base_imponible": n.base_imponible,
                "monto_iva": n.monto_iva,
                "monto_total": n.monto_total,
            }
            for n in notas
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
    {
        "fn": ventas_listar_notas_debito_fiscales,
        "name": "ventas_listar_notas_debito_fiscales",
        "scope": f"{_SCOPE}:read",
    },
]
