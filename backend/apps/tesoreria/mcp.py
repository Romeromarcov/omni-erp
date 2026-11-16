"""Herramientas MCP de Tesorería — Extractos y saldos bancarios consolidados (R-CODE-7 / ADR-003)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger("omni.mcp.tesoreria")

_SCOPE = "tesoreria"


def _ctx(capability_token: str, scope: str) -> dict[str, Any]:
    from apps.core.mcp_server import _require_scope, _resolve_token  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, scope)
    assert context is not None  # nosec B101
    return context


def _empresa_activa(empresa_id: str):
    from apps.core.models import Empresa  # noqa: PLC0415

    try:
        uuid.UUID(str(empresa_id))
    except (ValueError, TypeError) as exc:
        raise PermissionError("empresa_id inválido.") from exc

    empresa = Empresa.objects.filter(id_empresa=empresa_id, activo=True).first()
    if empresa is None:
        raise PermissionError("Empresa inactiva o no encontrada.")
    return empresa


def tesoreria_saldos_extractos(
    capability_token: str,
    empresa_id: str,
    cuenta_id: str | None = None,
) -> dict[str, Any]:
    """Devuelve los saldos consolidados en USD y VES y alertas de continuidad de extractos.

    Scope requerido: ``tesoreria:read``
    """
    from apps.tesoreria.extractos import (  # noqa: PLC0415
        consolidar_saldos_extractos,
        serializar_consolidado,
    )

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if str(empresa_id) != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")
    if cuenta_id:
        try:
            uuid.UUID(str(cuenta_id))
        except (ValueError, TypeError) as exc:
            raise ValueError("cuenta_id no es un UUID válido.") from exc

    empresa = _empresa_activa(ctx["empresa_id"])
    cons = consolidar_saldos_extractos(empresa, cuenta_id=cuenta_id)
    logger.info(
        "tesoreria_saldos_extractos | actor=%s | tenant=%s | cuentas=%d",
        ctx["actor_id"],
        ctx["tenant_id"],
        len(cons.cuentas),
    )
    return serializar_consolidado(cons)


def tesoreria_listar_extractos(
    capability_token: str,
    empresa_id: str,
    cuenta_id: str | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Lista los cortes de estado de cuenta activos importados para la empresa.

    Scope requerido: ``tesoreria:read``
    """
    from apps.tesoreria.models import ExtractoBancarioArchivo  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    if str(empresa_id) != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")
    if cuenta_id:
        try:
            uuid.UUID(str(cuenta_id))
        except (ValueError, TypeError) as exc:
            raise ValueError("cuenta_id no es un UUID válido.") from exc

    empresa = _empresa_activa(ctx["empresa_id"])
    try:
        limite_int = int(limite)
    except (TypeError, ValueError) as exc:
        raise ValueError("limite debe ser un entero válido.") from exc
    tope = max(1, min(limite_int, 200))
    qs = (
        ExtractoBancarioArchivo.objects.filter(id_empresa=empresa, activo=True)
        .select_related("id_cuenta_bancaria")
        .order_by("-fecha_hasta", "-fecha_creacion")
    )
    if cuenta_id:
        qs = qs.filter(id_cuenta_bancaria_id=uuid.UUID(str(cuenta_id)))

    items = list(qs[:tope])
    logger.info(
        "tesoreria_listar_extractos | actor=%s | tenant=%s | count=%d",
        ctx["actor_id"],
        ctx["tenant_id"],
        len(items),
    )
    return [
        {
            "id": str(a.id),
            "cuenta_id": str(a.id_cuenta_bancaria_id),
            "nombre_banco": a.id_cuenta_bancaria.nombre_banco,
            "numero_cuenta": a.id_cuenta_bancaria.numero_cuenta,
            "formato_banco": a.formato_banco,
            "nombre_archivo": a.nombre_archivo,
            "moneda": a.moneda,
            "fecha_desde": a.fecha_desde.isoformat() if a.fecha_desde else None,
            "fecha_hasta": a.fecha_hasta.isoformat() if a.fecha_hasta else None,
            "saldo_inicial": f"{a.saldo_inicial:.2f}" if a.saldo_inicial is not None else None,
            "saldo_final": f"{a.saldo_final:.2f}" if a.saldo_final is not None else None,
            "total_lineas": a.total_lineas,
            "lineas_nuevas": a.lineas_nuevas,
            "lineas_duplicadas": a.lineas_duplicadas,
            "cuadra": a.cuadra,
            "observaciones": a.observaciones,
        }
        for a in items
    ]


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": tesoreria_saldos_extractos,
        "name": "tesoreria_saldos_extractos",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": tesoreria_listar_extractos,
        "name": "tesoreria_listar_extractos",
        "scope": f"{_SCOPE}:read",
    },
]
