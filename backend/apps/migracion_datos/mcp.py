"""Herramientas MCP de ``apps/migracion_datos`` — Migrador 1-Click Odoo READ-ONLY / CSV VE (Plan 09 Fase 8.4)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import logging
from typing import Any
import uuid

from apps.core.exceptions import sanitize_mcp_error

from .migrador_1click import (
    MigracionError,
    listar_formatos_migracion,
    preview_migracion_1click,
)

logger = logging.getLogger("omni.mcp.migracion_datos")

_SCOPE = "migracion_datos"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def migracion_listar_formatos_1click(capability_token: str, empresa_id: str | None = None) -> dict[str, Any]:
    """Lista fuentes soportadas (Odoo read-only, Saint, Profit, Galac), entidades y mapeos. Scope: ``migracion_datos:read``."""
    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id):
        return listar_formatos_migracion()


def migracion_preview_1click(
    capability_token: str,
    empresa_id: str,
    fuente: str,
    entidad: str,
    contenido_csv: str | None = None,
    id_conector: str | None = None,
    limite: int = 200,
) -> dict[str, Any]:
    """Previsualiza migración 1-click desde Odoo (solo lectura) o CSV Saint/Profit/Galac sin escribir en BD. Scope: ``migracion_datos:read``."""
    from apps.core.models import Empresa  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        empresa = Empresa.objects.filter(pk=uuid.UUID(str(ctx["empresa_id"])), activo=True).first()
        if empresa is None:
            return {"error": "Empresa inactiva o no encontrada."}

        conector_uuid: uuid.UUID | None = None
        if id_conector:
            raw_cid = str(id_conector).strip()
            if "\x00" in raw_cid:
                return {"error": "id_conector inválido."}
            try:
                conector_uuid = uuid.UUID(raw_cid)
            except ValueError:
                return {"error": "id_conector no es un UUID válido."}

        try:
            return preview_migracion_1click(
                empresa,
                fuente=fuente,
                entidad=entidad,
                contenido_csv=contenido_csv,
                id_conector=conector_uuid,
                limite=limite,
            )
        except MigracionError as exc:
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="migracion_preview_1click",
                    controlled_types=(MigracionError, ValueError),
                )
            }


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": migracion_listar_formatos_1click,
        "name": "migracion_listar_formatos_1click",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": migracion_preview_1click,
        "name": "migracion_preview_1click",
        "scope": f"{_SCOPE}:read",
    },
]
