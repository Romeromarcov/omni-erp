"""
apps/inventario/mcp.py — Herramientas MCP del módulo de Inventario (ADR-003).

Herramientas expuestas:
  inventario_get_productos     — lista productos de una empresa
  inventario_get_stock_resumen — resumen de stock por almacén
  inventario_get_alertas_stock — productos con stock bajo el punto de reorden
"""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger("omni.mcp.inventario")

_SCOPE = "inventario"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def inventario_get_productos(
    capability_token: str,
    empresa_id: str,
    buscar: str = "",
    activos_solo: bool = True,
    limit: int = 50,
) -> list:
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

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        limit = min(limit, 200)
        qs = Producto.objects.filter(id_empresa=empresa_id)
        if activos_solo:
            qs = qs.filter(activo=True)
        if buscar:
            qs = qs.filter(nombre_producto__icontains=buscar)

        productos = qs.order_by("nombre_producto")[:limit]
        logger.info(
            "inventario_get_productos | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(productos),
        )
        return [
            {
                "id_producto": str(p.id_producto),
                "nombre_producto": p.nombre_producto,
                "sku": p.sku or "",
                # M-BUG-1: monetario como Decimal (no float) para no perder precisión.
                "precio_venta_sugerido": p.precio_venta_sugerido or Decimal("0"),
                "activo": p.activo,
            }
            for p in productos
        ]


def inventario_get_stock_resumen(
    capability_token: str,
    empresa_id: str,
    almacen_id: str = "",
) -> list:
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

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        qs = StockActual.objects.filter(
            id_empresa=empresa_id,
        ).select_related("id_producto", "id_almacen")
        if almacen_id:
            qs = qs.filter(id_almacen=almacen_id)

        logger.info(
            "inventario_get_stock_resumen | actor=%s | tenant=%s | almacen=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            almacen_id or "todos",
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
) -> list:
    """
    Retorna productos cuyo stock disponible cayó por debajo del punto de reorden.

    Scope requerido: ``inventario:read``

    Returns:
        Lista de productos con stock bajo, incluyendo stock_actual y punto_reorden.
    """
    from apps.inventario.models import StockActual  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        alertas = []
        stocks = (
            StockActual.objects.filter(id_empresa=empresa_id)
            .select_related("id_producto")
            .filter(id_producto__punto_reorden__isnull=False)
        )

        for s in stocks:
            prod = s.id_producto
            if prod.punto_reorden and s.cantidad_disponible <= prod.punto_reorden:
                alertas.append(
                    {
                        "producto_id": str(prod.id_producto),
                        "nombre": prod.nombre_producto,
                        "sku": prod.sku or "",
                        "stock_actual": float(s.cantidad_disponible),
                        "punto_reorden": float(prod.punto_reorden),
                        "deficit": float(prod.punto_reorden - s.cantidad_disponible),
                    }
                )

        logger.info(
            "inventario_get_alertas_stock | actor=%s | tenant=%s | alertas=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(alertas),
        )
        return alertas


def _parse_uuid_mcp(raw: str, campo: str) -> uuid.UUID:
    limpio = str(raw or "").strip()
    if not limpio or "\x00" in limpio:
        raise ValueError(f"El parámetro '{campo}' es inválido.")
    try:
        return uuid.UUID(limpio)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"El parámetro '{campo}' no es un UUID válido.") from exc


def inventario_evaluar_reabastecimiento(
    capability_token: str,
    empresa_id: str,
    almacen_id: str = "",
    solo_requieren: bool = True,
) -> Any:
    """Evalúa las reglas activas de reabastecimiento contra el stock proyectado de la empresa.

    Scope requerido: ``inventario:read``
    """
    from apps.almacenes.models import Almacen  # noqa: PLC0415
    from apps.core.models import Empresa  # noqa: PLC0415
    from apps.inventario.services_reabastecimiento import evaluar_reabastecimiento  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        try:
            emp_uuid = _parse_uuid_mcp(empresa_id, "empresa_id")
            empresa = Empresa.objects.filter(pk=emp_uuid, activo=True).first()
            if empresa is None:
                raise ValueError("Empresa no encontrada o inactiva.")

            almacen = None
            if almacen_id and str(almacen_id).strip():
                alm_uuid = _parse_uuid_mcp(almacen_id, "almacen_id")
                almacen = Almacen.objects.filter(pk=alm_uuid, id_empresa=empresa).first()
                if almacen is None:
                    raise ValueError("Almacén no encontrado en la empresa.")

            if not isinstance(solo_requieren, bool):
                raise ValueError("El parámetro 'solo_requieren' debe ser booleano.")

            resultados = evaluar_reabastecimiento(
                empresa,
                almacen=almacen,
                incluir_ok=not solo_requieren,
            )
        except ValueError as exc:
            return {"error": str(exc)}

        logger.info(
            "inventario_evaluar_reabastecimiento | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(resultados),
        )
        return [{k: str(v) if isinstance(v, Decimal) else v for k, v in item.items()} for item in resultados]


def inventario_consultar_lotes(
    capability_token: str,
    empresa_id: str,
    producto_id: str = "",
    almacen_id: str = "",
    por_vencer_dias: int | None = None,
    solo_con_stock: bool = True,
) -> Any:
    """Lista los lotes de producto de la empresa con filtros opcionales por producto, almacén y vencimiento.

    Scope requerido: ``inventario:read``
    """
    from apps.almacenes.models import Almacen  # noqa: PLC0415
    from apps.core.models import Empresa  # noqa: PLC0415
    from apps.inventario.models import LoteProducto, Producto  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        try:
            emp_uuid = _parse_uuid_mcp(empresa_id, "empresa_id")
            empresa = Empresa.objects.filter(pk=emp_uuid, activo=True).first()
            if empresa is None:
                raise ValueError("Empresa no encontrada o inactiva.")

            producto = None
            if producto_id and str(producto_id).strip():
                prod_uuid = _parse_uuid_mcp(producto_id, "producto_id")
                producto = Producto.objects.filter(pk=prod_uuid, id_empresa=empresa).first()
                if producto is None:
                    raise ValueError("Producto no encontrado en la empresa.")

            almacen = None
            if almacen_id and str(almacen_id).strip():
                alm_uuid = _parse_uuid_mcp(almacen_id, "almacen_id")
                almacen = Almacen.objects.filter(pk=alm_uuid, id_empresa=empresa).first()
                if almacen is None:
                    raise ValueError("Almacén no encontrado en la empresa.")

            dias_int: int | None = None
            limite = None
            if por_vencer_dias is not None:
                if isinstance(por_vencer_dias, bool):
                    raise ValueError("El parámetro 'por_vencer_dias' debe ser un entero >= 0.")
                try:
                    dias_int = int(por_vencer_dias)
                except (ValueError, TypeError) as exc:
                    raise ValueError("El parámetro 'por_vencer_dias' debe ser un entero >= 0.") from exc
                if dias_int < 0 or dias_int > 36500:
                    raise ValueError("El parámetro 'por_vencer_dias' debe estar entre 0 y 36500.")
                try:
                    limite = timezone.localdate() + timedelta(days=dias_int)
                except (OverflowError, ValueError) as exc:
                    raise ValueError("El parámetro 'por_vencer_dias' está fuera de rango.") from exc

            if not isinstance(solo_con_stock, bool):
                raise ValueError("El parámetro 'solo_con_stock' debe ser booleano.")
        except (ValueError, OverflowError) as exc:
            return {"error": str(exc)}

        qs = LoteProducto.objects.filter(id_empresa=empresa, activo=True).select_related(
            "id_producto", "id_almacen", "id_variante"
        )
        if producto is not None:
            qs = qs.filter(id_producto=producto)
        if almacen is not None:
            qs = qs.filter(id_almacen=almacen)
        if solo_con_stock:
            qs = qs.filter(cantidad_disponible__gt=0)
        if limite is not None:
            qs = qs.filter(fecha_vencimiento__isnull=False, fecha_vencimiento__lte=limite)

        lotes = list(qs.order_by(F("fecha_vencimiento").asc(nulls_last=True), "numero_lote", "pk")[:200])
        logger.info(
            "inventario_consultar_lotes | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(lotes),
        )
        return [
            {
                "id_lote": str(lote.id_lote),
                "id_producto": str(lote.id_producto_id),
                "producto_nombre": lote.id_producto.nombre_producto,
                "sku": lote.id_producto.sku or "",
                "id_variante": str(lote.id_variante_id) if lote.id_variante_id else None,
                "id_almacen": str(lote.id_almacen_id),
                "almacen_nombre": lote.id_almacen.nombre_almacen,
                "numero_lote": lote.numero_lote,
                "fecha_fabricacion": lote.fecha_fabricacion.isoformat() if lote.fecha_fabricacion else None,
                "fecha_vencimiento": lote.fecha_vencimiento.isoformat() if lote.fecha_vencimiento else None,
                "cantidad_disponible": str(lote.cantidad_disponible.quantize(Decimal("0.0001"))),
                "cantidad_reservada": str(lote.cantidad_reservada.quantize(Decimal("0.0001"))),
                "cantidad_libre": str(
                    (lote.cantidad_disponible - lote.cantidad_reservada).quantize(Decimal("0.0001"))
                ),
            }
            for lote in lotes
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Auto-discovery
# ─────────────────────────────────────────────────────────────────────────────

MCP_TOOLS: List[Dict[str, Any]] = [
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
    {
        "fn": inventario_evaluar_reabastecimiento,
        "name": "inventario_evaluar_reabastecimiento",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": inventario_consultar_lotes,
        "name": "inventario_consultar_lotes",
        "scope": f"{_SCOPE}:read",
    },
]
