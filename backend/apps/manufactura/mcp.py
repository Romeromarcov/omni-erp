"""
apps/manufactura/mcp.py — Herramientas MCP del módulo de Manufactura (R-CODE-7).

Herramientas expuestas:
  manufactura_calcular_mrp      — MRP básico: faltantes para producir X unidades
  manufactura_get_costeo_orden  — costeo real de una orden de producción
"""

import logging
import uuid as uuid_lib
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

logger = logging.getLogger("omni.mcp.manufactura")

_SCOPE = "manufactura"


def _ctx(capability_token: str, scope: str) -> dict:
    from apps.core.mcp_server import _require_scope, _resolve_token  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, scope)
    assert context is not None  # noqa: S101
    return context


def manufactura_calcular_mrp(
    capability_token: str,
    empresa_id: str,
    lista_materiales_id: str,
    cantidad: str,
    almacen_id: str = "",
) -> dict:
    """
    MRP básico: materiales necesarios para producir `cantidad` unidades con una
    lista de materiales (BOM), comparados contra el stock actual de la empresa.

    Scope requerido: ``manufactura:read``

    Args:
        capability_token:    Token con scope ``manufactura:read``.
        empresa_id:          ID de la empresa (debe coincidir con el tenant).
        lista_materiales_id: ID de la ListaMateriales (BOM) a explotar.
        cantidad:            Unidades a producir (decimal en string).
        almacen_id:          Limitar el stock a un almacén (opcional).

    Returns:
        Dict con la lista de faltantes: producto, requerido, disponible, a_comprar
        (montos/cantidades como string Decimal — R-CODE-4).
    """
    from apps.almacenes.models import Almacen  # noqa: PLC0415
    from apps.manufactura import services  # noqa: PLC0415
    from apps.manufactura.models import ListaMateriales  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    try:
        cant = Decimal(str(cantidad))
    except InvalidOperation as exc:
        raise ValueError("'cantidad' no es un número válido.") from exc

    # R-CODE-1: la BOM y el almacén deben pertenecer al tenant del token.
    lista = ListaMateriales.objects.filter(pk=lista_materiales_id, empresa_id=empresa_id).first()
    if lista is None:
        raise ValueError("Lista de materiales no encontrada en la empresa.")
    almacen = None
    if almacen_id:
        almacen = Almacen.objects.filter(pk=almacen_id, id_empresa_id=uuid_lib.UUID(empresa_id)).first()
        if almacen is None:
            raise ValueError("Almacén no encontrado en la empresa.")

    faltantes = services.calcular_mrp_lista(lista, cant, almacen=almacen)
    logger.info(
        "manufactura_calcular_mrp | actor=%s | tenant=%s | lista=%s | cantidad=%s",
        ctx["actor_id"], ctx["tenant_id"], lista_materiales_id, cant,
    )
    return {
        "lista_materiales_id": str(lista.pk),
        "cantidad": str(cant),
        "faltantes": [
            {
                "producto_id": f["producto_id"],
                "producto": f["producto"],
                "requerido": str(f["requerido"]),
                "disponible": str(f["disponible"]),
                "a_comprar": str(f["a_comprar"]),
            }
            for f in faltantes
        ],
    }


def manufactura_get_costeo_orden(
    capability_token: str,
    empresa_id: str,
    orden_id: str,
) -> dict:
    """
    Costeo real de una orden de producción: materiales consumidos (al costo del
    movimiento de inventario) + mano de obra de etapas + overhead configurable.

    Scope requerido: ``manufactura:read``

    Returns:
        Dict con costo_materiales, mano_obra, costos_indirectos, costo_total y
        costo_unitario (string Decimal — R-CODE-4) + estado y etapas de la OF.
    """
    from apps.manufactura import services  # noqa: PLC0415
    from apps.manufactura.models import OrdenProduccion  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    orden = OrdenProduccion.objects.filter(pk=orden_id, empresa_id=empresa_id).first()
    if orden is None:
        raise ValueError("Orden de producción no encontrada en la empresa.")

    costo = services.costeo_real_orden(orden)
    logger.info(
        "manufactura_get_costeo_orden | actor=%s | tenant=%s | orden=%s",
        ctx["actor_id"], ctx["tenant_id"], orden_id,
    )
    return {
        "orden_id": str(orden.pk),
        "estado": orden.estado,
        "costo": {k: str(v) for k, v in costo.items()},
        "etapas": [
            {
                "orden": e.orden,
                "etapa": e.etapa.nombre,
                "estado": e.estado,
                "costo_mano_obra": str(e.costo_mano_obra),
            }
            for e in orden.etapas.select_related("etapa").order_by("orden")
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Auto-discovery
# ─────────────────────────────────────────────────────────────────────────────

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "fn": manufactura_calcular_mrp,
        "name": "manufactura_calcular_mrp",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": manufactura_get_costeo_orden,
        "name": "manufactura_get_costeo_orden",
        "scope": f"{_SCOPE}:read",
    },
]
