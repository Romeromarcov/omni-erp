"""
apps/fiscal/mcp.py — Herramientas MCP del módulo Fiscal (ADR-003).

Herramientas expuestas:
  fiscal_parafiscales_pendientes — pagos de contribuciones parafiscales por pagar
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Dict, List

logger = logging.getLogger("omni.mcp.fiscal")

_SCOPE = "fiscal"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


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

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
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
            ctx["actor_id"],
            ctx["tenant_id"],
            len(pagos),
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
