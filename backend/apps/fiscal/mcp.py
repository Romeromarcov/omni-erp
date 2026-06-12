"""
apps/fiscal/mcp.py — Herramientas MCP del módulo Fiscal (ADR-003).

Herramientas expuestas:
  fiscal_parafiscales_pendientes — pagos de contribuciones parafiscales por pagar
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger("omni.mcp.fiscal")

_SCOPE = "fiscal"


def _ctx(capability_token: str, scope: str) -> dict:
    from apps.core.mcp_server import _require_scope, _resolve_token  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, scope)
    assert context is not None  # noqa: S101
    return context


def fiscal_parafiscales_pendientes(
    capability_token: str,
    empresa_id: str,
    limit: int = 50,
) -> list:
    """
    Lista los pagos de contribuciones parafiscales (IVSS, FAOV, INCES…, §6.7
    Capa B) que siguen en estado ``pendiente`` (declarados y sin pagar).

    Scope requerido: ``fiscal:read``

    Args:
        capability_token: Token con scope ``fiscal:read``.
        empresa_id:       ID de la empresa.
        limit:            Máximo de resultados (default 50, máx 200).

    Returns:
        Lista con id, contribución (código/nombre/tipo), período (YYYY-MM),
        monto, moneda, referencia y proceso de nómina origen si existe.
    """
    from apps.fiscal.models import PagoContribucionParafiscal  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    limit = min(limit, 200)
    pagos = (
        PagoContribucionParafiscal.objects.filter(
            id_empresa=empresa_id,
            estado="pendiente",
            activo=True,
        )
        .select_related("contribucion", "id_moneda")
        .order_by("periodo_año", "periodo_mes", "fecha_creacion")[:limit]
    )
    logger.info(
        "fiscal_parafiscales_pendientes | actor=%s | tenant=%s | count=%d",
        ctx["actor_id"], ctx["tenant_id"], len(pagos),
    )
    return [
        {
            "id_pago_parafiscal": str(p.id_pago_parafiscal),
            "contribucion_codigo": p.contribucion.codigo,
            "contribucion_nombre": p.contribucion.nombre,
            "contribucion_tipo": p.contribucion.tipo,
            "periodo": p.periodo,
            "monto": p.monto,  # Decimal, no float (R-CODE-4)
            "moneda": p.id_moneda.codigo_iso if p.id_moneda else "",
            "referencia": p.referencia,
            "proceso_nomina_id": str(p.id_proceso_nomina_id) if p.id_proceso_nomina_id else "",
            "estado": p.estado,
        }
        for p in pagos
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Auto-discovery
# ─────────────────────────────────────────────────────────────────────────────

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "fn": fiscal_parafiscales_pendientes,
        "name": "fiscal_parafiscales_pendientes",
        "scope": f"{_SCOPE}:read",
    },
]
