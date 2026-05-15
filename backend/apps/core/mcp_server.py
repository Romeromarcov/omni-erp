"""
Omni MCP Server — Núcleo de capacidades AI-nativas.

Expone las capacidades de Omni como herramientas MCP (Model Context Protocol).
Los agentes externos o internos pueden llamar a estas herramientas para
interactuar con el sistema de forma controlada y auditable.

Principios (ADR-003):
  - Sin acceso por defecto. Cada llamada requiere un CapabilityToken válido.
  - Scope mínimo por herramienta.
  - Audit log completo de cada llamada.
  - Rate limiting agresivo (configurado en el gateway, no aquí).

Arranque del servidor MCP:
  python manage.py run_mcp_server           (stdio, para Claude Desktop)
  python manage.py run_mcp_server --sse     (SSE, para clientes HTTP)

Herramientas disponibles (v0 — solo lectura):
  - omni_ping              : health check
  - omni_get_empresas      : lista empresas del tenant
  - omni_get_clientes      : lista clientes de una empresa
  - omni_get_productos     : lista productos de una empresa
  - omni_get_saldo_cliente : saldo CxC de un cliente específico
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import django

# Asegurar que Django esté inicializado cuando se importa este módulo
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_dev")
try:
    django.setup()
except RuntimeError:
    # Ya inicializado (entorno de test o servidor Django corriendo)
    pass

logger = logging.getLogger("omni.mcp")

# ── Importar mcp después de Django setup ─────────────────────────────────────
try:
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("mcp SDK no disponible; MCP server en modo stub")

# ── Instancia del servidor MCP ────────────────────────────────────────────────

if MCP_AVAILABLE:
    mcp = FastMCP(
        name="omni-erp",
        instructions=(
            "Omni ERP AI-native server. "
            "Todas las operaciones requieren un capability_token válido con el scope adecuado. "
            "Los datos devueltos son siempre del tenant correspondiente al token."
        ),
    )
else:
    mcp = None  # type: ignore[assignment]


# ── Helpers de autenticación ─────────────────────────────────────────────────

def _resolve_token(capability_token: str) -> dict[str, Any] | None:
    """
    Valida un CapabilityToken y devuelve el contexto del tenant.

    Returns:
        dict con {tenant_id, empresa_id, actor_id, scopes} o None si inválido.
    """
    from apps.core.models import CapabilityToken  # noqa: PLC0415

    try:
        # Validar que el string sea un UUID válido antes de consultar la BD
        uuid.UUID(capability_token)
    except (ValueError, AttributeError):
        return None

    try:
        token_obj = CapabilityToken.objects.select_related("empresa").get(
            token=capability_token,
            activo=True,
        )
    except CapabilityToken.DoesNotExist:
        return None

    if token_obj.is_expired():
        return None

    return {
        "tenant_id": str(token_obj.empresa.id_empresa),
        "empresa_id": str(token_obj.empresa.id_empresa),
        "actor_id": f"mcp-token:{str(token_obj.token)[:8]}",
        "scopes": token_obj.scopes,
    }


def _require_scope(context: dict[str, Any] | None, scope: str) -> None:
    """Lanza PermissionError si el contexto no tiene el scope requerido."""
    if context is None:
        raise PermissionError("Token de capacidad inválido o expirado.")
    if scope not in context["scopes"] and "*" not in context["scopes"]:
        raise PermissionError(f"El token no tiene el scope requerido: {scope}")


# ── Herramientas MCP ──────────────────────────────────────────────────────────

if MCP_AVAILABLE and mcp is not None:

    @mcp.tool()
    def omni_ping(capability_token: str) -> dict[str, Any]:
        """
        Health check del servidor Omni.

        Args:
            capability_token: Token de capacidad válido (cualquier scope).

        Returns:
            dict con status y versión.
        """
        context = _resolve_token(capability_token)
        if context is None:
            raise PermissionError("Token inválido.")

        logger.info("omni_ping | actor=%s | tenant=%s", context["actor_id"], context["tenant_id"])
        return {
            "status": "ok",
            "version": "0.1.0",
            "tenant_id": context["tenant_id"],
        }

    @mcp.tool()
    def omni_get_empresas(capability_token: str) -> list[dict[str, Any]]:
        """
        Lista las empresas visibles para el tenant del token.

        Scope requerido: `core:read`

        Args:
            capability_token: Token de capacidad con scope `core:read`.

        Returns:
            Lista de empresas con id, nombre_comercial, rif, activo.
        """
        from apps.core.models import Empresa  # noqa: PLC0415

        context = _resolve_token(capability_token)
        _require_scope(context, "core:read")
        assert context is not None  # noqa: S101 — checked by _require_scope

        empresas = Empresa.objects.filter(
            id_empresa=context["empresa_id"],
            activo=True,
        ).values("id_empresa", "nombre_comercial", "rif", "activo")

        logger.info(
            "omni_get_empresas | actor=%s | tenant=%s | count=%d",
            context["actor_id"],
            context["tenant_id"],
            len(empresas),
        )
        return [
            {
                "id_empresa": str(e["id_empresa"]),
                "nombre_comercial": e["nombre_comercial"],
                "rif": e.get("rif", ""),
                "activo": e["activo"],
            }
            for e in empresas
        ]

    @mcp.tool()
    def omni_get_clientes(
        capability_token: str,
        empresa_id: str,
        buscar: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Lista los clientes de una empresa.

        Scope requerido: `crm:read`

        Args:
            capability_token: Token de capacidad con scope `crm:read`.
            empresa_id:       ID de la empresa (debe coincidir con el tenant del token).
            buscar:           Texto libre para filtrar por nombre o RIF (opcional).
            limit:            Máximo de resultados a devolver (default 50, máx 200).

        Returns:
            Lista de clientes con id, razon_social, rif, activo.
        """
        from apps.crm.models import Cliente  # noqa: PLC0415

        context = _resolve_token(capability_token)
        _require_scope(context, "crm:read")
        assert context is not None  # noqa: S101

        # Verificar que el empresa_id corresponde al tenant del token
        if empresa_id != context["empresa_id"]:
            raise PermissionError("empresa_id no coincide con el tenant del token.")

        limit = min(limit, 200)  # cap duro
        qs = Cliente.objects.filter(
            id_empresa=empresa_id,
            activo=True,
        )
        if buscar:
            from django.db.models import Q  # noqa: PLC0415

            qs = qs.filter(
                Q(razon_social__icontains=buscar) | Q(rif__icontains=buscar)
            )

        clientes = qs.values("id_cliente", "razon_social", "rif", "activo")[:limit]

        logger.info(
            "omni_get_clientes | actor=%s | tenant=%s | empresa=%s | count=%d",
            context["actor_id"],
            context["tenant_id"],
            empresa_id,
            len(clientes),
        )
        return [
            {
                "id_cliente": str(c["id_cliente"]),
                "razon_social": c["razon_social"],
                "rif": c.get("rif", ""),
                "activo": c["activo"],
            }
            for c in clientes
        ]

    @mcp.tool()
    def omni_get_saldo_cliente(
        capability_token: str,
        empresa_id: str,
        cliente_id: str,
    ) -> dict[str, Any]:
        """
        Devuelve el saldo pendiente de CxC de un cliente.

        Scope requerido: `cxc:read`

        Args:
            capability_token: Token con scope `cxc:read`.
            empresa_id:       ID de la empresa.
            cliente_id:       ID del cliente.

        Returns:
            dict con total_pendiente, cantidad_facturas, moneda_base.
        """
        from django.db.models import Sum  # noqa: PLC0415

        from apps.cuentas_por_cobrar.models import CuentaPorCobrar  # noqa: PLC0415

        context = _resolve_token(capability_token)
        _require_scope(context, "cxc:read")
        assert context is not None  # noqa: S101

        if empresa_id != context["empresa_id"]:
            raise PermissionError("empresa_id no coincide con el tenant del token.")

        resultado = CuentaPorCobrar.objects.filter(
            id_empresa=empresa_id,
            id_cliente=cliente_id,
            estado__in=["PENDIENTE", "PARCIAL"],
        ).aggregate(
            total_pendiente=Sum("saldo_pendiente"),
            cantidad_facturas=Sum("id_cxc"),  # hack: cuenta rows
        )

        total = resultado["total_pendiente"] or 0
        logger.info(
            "omni_get_saldo_cliente | actor=%s | tenant=%s | cliente=%s | saldo=%s",
            context["actor_id"],
            context["tenant_id"],
            cliente_id,
            total,
        )
        return {
            "cliente_id": cliente_id,
            "empresa_id": empresa_id,
            "total_pendiente": float(total),
            "moneda_base": "USD",  # TODO: leer de configuración del tenant
        }
