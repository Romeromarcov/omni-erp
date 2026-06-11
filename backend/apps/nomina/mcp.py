"""
apps/nomina/mcp.py — Herramientas MCP del módulo de Nómina (ADR-003, R-CODE-7).

Descubiertas automáticamente por apps/core/mcp_server.py (patrón MCP_TOOLS).

Herramientas expuestas:
  nomina_procesar_proceso — procesa la nómina LOTTT de un proceso (scope nomina:write)
  nomina_resumen_proceso  — resumen de totales/recibos de un proceso (scope nomina:read)
"""

import logging
import uuid
from typing import Any, Dict, List

logger = logging.getLogger("omni.mcp.nomina")

# Scope prefix para este módulo
_SCOPE = "nomina"


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


def nomina_procesar_proceso(
    capability_token: str,
    empresa_id: str,
    proceso_id: str,
) -> dict:
    """
    Procesa la nómina LOTTT de un ProcesoNomina: calcula y persiste los recibos
    de cada empleado activo, totaliza el proceso y genera el asiento NOMINA
    (todo atómico, R-CODE-11).

    Scope requerido: ``nomina:write``

    Args:
        capability_token: Token con scope ``nomina:write``.
        empresa_id:       ID de la empresa (tenant).
        proceso_id:       UUID del ProcesoNomina (debe estar EN_PROCESO).

    Returns:
        dict con totales del proceso y el asiento generado, o {"error": ...}.
    """
    from apps.contabilidad.services import AsientoError  # noqa: PLC0415
    from apps.nomina.models import ProcesoNomina  # noqa: PLC0415
    from apps.nomina.services import NominaProcesoError, procesar_proceso_nomina  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:write")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    try:
        proceso = ProcesoNomina.objects.get(pk=proceso_id, id_empresa=uuid.UUID(empresa_id))
    except (ProcesoNomina.DoesNotExist, ValueError):
        return {"error": f"Proceso de nómina {proceso_id} no encontrado."}

    try:
        proceso, asiento, advertencia = procesar_proceso_nomina(proceso)
    except (NominaProcesoError, AsientoError) as exc:
        return {"error": str(exc)}

    logger.info(
        "nomina_procesar_proceso | actor=%s | tenant=%s | proceso=%s",
        ctx["actor_id"], ctx["tenant_id"], proceso_id,
    )
    return {
        "id_proceso_nomina": str(proceso.id_proceso_nomina),
        "numero_proceso": proceso.numero_proceso,
        "estado": proceso.estado,
        "total_empleados": proceso.total_empleados,
        "total_devengado": str(proceso.total_devengado),
        "total_deducciones": str(proceso.total_deducciones),
        "total_neto": str(proceso.total_neto),
        "asiento_contable": str(asiento.id_asiento) if asiento else None,
        "advertencia_asiento": advertencia,
    }


def nomina_resumen_proceso(
    capability_token: str,
    empresa_id: str,
    proceso_id: str,
) -> dict:
    """
    Devuelve el resumen de un proceso de nómina: totales y recibos por empleado.

    Scope requerido: ``nomina:read``

    Args:
        capability_token: Token con scope ``nomina:read``.
        empresa_id:       ID de la empresa (tenant).
        proceso_id:       UUID del ProcesoNomina.

    Returns:
        dict con estado, totales y lista de recibos (Nomina) del proceso.
    """
    from apps.nomina.models import ProcesoNomina  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if empresa_id != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    try:
        proceso = ProcesoNomina.objects.prefetch_related("nominas__id_empleado").get(
            pk=proceso_id, id_empresa=uuid.UUID(empresa_id)
        )
    except (ProcesoNomina.DoesNotExist, ValueError):
        return {"error": f"Proceso de nómina {proceso_id} no encontrado."}

    logger.info(
        "nomina_resumen_proceso | actor=%s | tenant=%s | proceso=%s",
        ctx["actor_id"], ctx["tenant_id"], proceso_id,
    )
    return {
        "id_proceso_nomina": str(proceso.id_proceso_nomina),
        "numero_proceso": proceso.numero_proceso,
        "estado": proceso.estado,
        "total_empleados": proceso.total_empleados,
        "total_devengado": str(proceso.total_devengado),
        "total_deducciones": str(proceso.total_deducciones),
        "total_neto": str(proceso.total_neto),
        "recibos": [
            {
                "id_nomina": str(n.id_nomina),
                "empleado": f"{n.id_empleado.nombre} {n.id_empleado.apellido}",
                "cedula": n.id_empleado.cedula,
                "sueldo_base": str(n.sueldo_base),
                "total_devengado": str(n.total_devengado),
                "total_deducciones": str(n.total_deducciones),
                "total_neto": str(n.total_neto),
                "estado": n.estado,
            }
            for n in proceso.nominas.all()
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Auto-discovery
# ─────────────────────────────────────────────────────────────────────────────

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "fn": nomina_procesar_proceso,
        "name": "nomina_procesar_proceso",
        "scope": f"{_SCOPE}:write",
    },
    {
        "fn": nomina_resumen_proceso,
        "name": "nomina_resumen_proceso",
        "scope": f"{_SCOPE}:read",
    },
]
