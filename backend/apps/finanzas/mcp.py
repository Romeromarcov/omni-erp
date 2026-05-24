"""
apps/finanzas/mcp.py — Herramientas MCP del módulo de Finanzas (ADR-003).

Herramientas expuestas:
  finanzas_get_pagos          — lista pagos registrados de una empresa
  finanzas_get_saldo_caja     — saldo actual de una caja física
  finanzas_get_metodos_pago   — lista métodos de pago disponibles
"""


import logging
from typing import Any, Dict, List

logger = logging.getLogger("omni.mcp.finanzas")

_SCOPE = "finanzas"


def _ctx(capability_token: str, scope: str) -> dict:
    from apps.core.mcp_server import _require_scope, _resolve_token  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, scope)
    assert context is not None  # noqa: S101
    return context


def finanzas_get_pagos(
    capability_token: str,
    empresa_id: str,
    tipo_documento: str = "",
    limit: int = 50,
) -> list:
    """
    Lista pagos registrados de una empresa.

    Scope requerido: ``finanzas:read``

    Args:
        capability_token: Token con scope ``finanzas:read``.
        empresa_id:       ID de la empresa.
        tipo_documento:   Filtrar por tipo (PEDIDO, NOTA_VENTA, FACTURA_FISCAL). Vacío = todos.
        limit:            Máximo de resultados (default 50, máx 200).

    Returns:
        Lista de pagos con id, monto, metodo, moneda, tipo_documento, referencia.
    """
    from apps.finanzas.models import Pago  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    limit = min(limit, 200)
    qs = Pago.objects.filter(
        id_empresa=empresa_id,
    ).select_related("id_metodo_pago", "id_moneda")
    if tipo_documento:
        qs = qs.filter(tipo_documento=tipo_documento)

    pagos = qs.order_by("-fecha_pago")[:limit]
    logger.info(
        "finanzas_get_pagos | actor=%s | tenant=%s | count=%d",
        ctx["actor_id"], ctx["tenant_id"], len(pagos),
    )
    return [
        {
            "id_pago": str(p.id_pago),
            "monto": float(p.monto),
            "moneda": p.id_moneda.codigo_iso if p.id_moneda else "",
            "metodo": p.id_metodo_pago.nombre_metodo if p.id_metodo_pago else "",
            "tipo_documento": p.tipo_documento or "",
            "id_documento": str(p.id_documento) if p.id_documento else "",
            "referencia": p.referencia or "",
            "fecha": str(p.fecha_pago) if p.fecha_pago else "",
        }
        for p in pagos
    ]


def finanzas_get_saldo_caja(
    capability_token: str,
    empresa_id: str,
    caja_id: str,
) -> dict:
    """
    Retorna el saldo actual de una caja física específica.

    Scope requerido: ``finanzas:read``

    Args:
        capability_token: Token con scope ``finanzas:read``.
        empresa_id:       ID de la empresa.
        caja_id:          UUID de la CajaFisica.

    Returns:
        dict con caja_id, nombre, saldo_apertura, total_ingresos, total_egresos, saldo_actual.
    """
    from apps.finanzas.models import CajaFisica  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    try:
        caja = CajaFisica.objects.get(pk=caja_id, id_empresa=empresa_id)
    except CajaFisica.DoesNotExist:
        return {"error": f"Caja {caja_id} no encontrada."}

    logger.info(
        "finanzas_get_saldo_caja | actor=%s | tenant=%s | caja=%s",
        ctx["actor_id"], ctx["tenant_id"], caja_id,
    )

    # Obtener la sesión activa si existe
    sesion_activa = caja.sesiones.filter(fecha_cierre__isnull=True).first()
    saldo_apertura = float(sesion_activa.monto_apertura) if sesion_activa else 0.0

    return {
        "caja_id": str(caja.id_caja_fisica),
        "nombre": caja.nombre,
        "activa": caja.activo,
        "sesion_activa": sesion_activa is not None,
        "saldo_apertura": saldo_apertura,
    }


def finanzas_get_metodos_pago(
    capability_token: str,
) -> list:
    """
    Lista todos los métodos de pago disponibles en el sistema.

    Scope requerido: ``finanzas:read``

    Returns:
        Lista de métodos con id, nombre, tipo_metodo.
    """
    from apps.finanzas.models import MetodoPago  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    metodos = MetodoPago.objects.filter(activo=True).order_by("nombre_metodo")
    logger.info(
        "finanzas_get_metodos_pago | actor=%s | tenant=%s | count=%d",
        ctx["actor_id"], ctx["tenant_id"], len(metodos),
    )
    return [
        {
            "id_metodo_pago": str(m.id_metodo_pago),
            "nombre_metodo": m.nombre_metodo,
            "tipo_metodo": m.tipo_metodo,
        }
        for m in metodos
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Auto-discovery
# ─────────────────────────────────────────────────────────────────────────────

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "fn": finanzas_get_pagos,
        "name": "finanzas_get_pagos",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": finanzas_get_saldo_caja,
        "name": "finanzas_get_saldo_caja",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": finanzas_get_metodos_pago,
        "name": "finanzas_get_metodos_pago",
        "scope": f"{_SCOPE}:read",
    },
]
