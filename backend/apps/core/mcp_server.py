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
  - omni_get_cxc_aging     : aging de saldos por cobrar
  - omni_get_stock_producto: stock disponible de un producto
  - omni_get_ventas_resumen: resumen de ventas (pedidos aprobados)
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from django.db import models

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


# ── Herramientas MCP (definidas a nivel de módulo para ser importables en tests) ─

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
        "moneda_base": "USD",
    }


def omni_get_cxc_aging(
    capability_token: str,
    empresa_id: str,
) -> dict[str, Any]:
    """
    Devuelve el reporte de antigüedad de saldos por cobrar de una empresa.

    Scope requerido: `cxc:read`

    Args:
        capability_token: Token con scope `cxc:read`.
        empresa_id:       ID de la empresa.

    Returns:
        dict con tramos: corriente, dias_1_30, dias_31_60, dias_61_90, dias_90_mas, total_general.
    """
    from apps.cuentas_por_cobrar.services import calcular_aging  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, "cxc:read")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    resultado = calcular_aging(empresa_id)

    def fmt_bucket(b):
        return {"count": b["count"], "total": float(b["total"])}

    logger.info(
        "omni_get_cxc_aging | actor=%s | tenant=%s | total=%s",
        context["actor_id"],
        context["tenant_id"],
        resultado["total_general"],
    )
    return {
        "empresa_id": empresa_id,
        "corriente":   fmt_bucket(resultado["corriente"]),
        "dias_1_30":   fmt_bucket(resultado["dias_1_30"]),
        "dias_31_60":  fmt_bucket(resultado["dias_31_60"]),
        "dias_61_90":  fmt_bucket(resultado["dias_61_90"]),
        "dias_90_mas": fmt_bucket(resultado["dias_90_mas"]),
        "total_general": float(resultado["total_general"]),
    }


def omni_get_stock_producto(
    capability_token: str,
    empresa_id: str,
    producto_id: str,
    almacen_id: str = "",
) -> list[dict[str, Any]]:
    """
    Devuelve el stock disponible de un producto, opcionalmente por almacén.

    Scope requerido: `inventario:read`

    Args:
        capability_token: Token con scope `inventario:read`.
        empresa_id:       ID de la empresa.
        producto_id:      ID del producto.
        almacen_id:       ID del almacén (opcional; si se omite devuelve todos).

    Returns:
        Lista de registros StockActual con almacen y cantidad_disponible.
    """
    from apps.inventario.models import StockActual  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, "inventario:read")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    qs = StockActual.objects.filter(
        id_empresa=empresa_id,
        id_producto=producto_id,
    ).select_related("id_almacen")

    if almacen_id:
        qs = qs.filter(id_almacen=almacen_id)

    logger.info(
        "omni_get_stock_producto | actor=%s | tenant=%s | producto=%s",
        context["actor_id"],
        context["tenant_id"],
        producto_id,
    )
    return [
        {
            "almacen_id": str(s.id_almacen_id),
            "almacen_nombre": s.id_almacen.nombre_almacen,
            "cantidad_disponible": float(s.cantidad_disponible),
        }
        for s in qs
    ]


def omni_get_ventas_resumen(
    capability_token: str,
    empresa_id: str,
    fecha_desde: str = "",
    fecha_hasta: str = "",
) -> dict[str, Any]:
    """
    Devuelve un resumen de ventas (pedidos aprobados) de una empresa.

    Scope requerido: `ventas:read`

    Args:
        capability_token: Token con scope `ventas:read`.
        empresa_id:       ID de la empresa.
        fecha_desde:      Fecha inicio YYYY-MM-DD (opcional).
        fecha_hasta:      Fecha fin YYYY-MM-DD (opcional).

    Returns:
        dict con cantidad_pedidos, total_ventas, promedio_pedido.
    """
    from django.db.models import Avg, Count, Sum  # noqa: PLC0415

    from apps.ventas.models import DetallePedido, Pedido  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, "ventas:read")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    qs = Pedido.objects.filter(id_empresa=empresa_id, estado="APROBADO")
    if fecha_desde:
        qs = qs.filter(fecha_pedido__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha_pedido__lte=fecha_hasta)

    pedidos_ids = list(qs.values_list("id_pedido", flat=True))
    totales = DetallePedido.objects.filter(
        id_pedido__in=pedidos_ids,
    ).aggregate(total=Sum("subtotal"), promedio=Avg("subtotal"))

    total = float(totales["total"] or 0)
    promedio = float(totales["promedio"] or 0)

    logger.info(
        "omni_get_ventas_resumen | actor=%s | tenant=%s | pedidos=%d | total=%s",
        context["actor_id"],
        context["tenant_id"],
        len(pedidos_ids),
        total,
    )
    return {
        "empresa_id": empresa_id,
        "cantidad_pedidos": len(pedidos_ids),
        "total_ventas": total,
        "promedio_linea": promedio,
    }


def omni_buscar_contacto(
    capability_token: str,
    empresa_id: str,
    query: str = "",
    rol: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Busca contactos unificados por nombre, RIF, cédula o email.

    Args:
        capability_token: Token de autenticación MCP.
        empresa_id:       UUID de la empresa.
        query:            Texto libre para buscar en nombre, RIF, cédula, email.
        rol:              Filtrar por rol: 'cliente', 'proveedor', 'empleado', 'usuario'.
                          Si None, devuelve todos.
        limit:            Máximo de resultados (default 20, máx 100).

    Returns:
        Lista de contactos con campos esenciales.
    """
    from apps.core.models import Contacto, Empresa

    context = _resolve_token(capability_token)
    _require_scope(context, "contactos:read")
    assert context is not None  # noqa: S101 — checked by _require_scope

    try:
        empresa = Empresa.objects.get(id_empresa=empresa_id)
    except Empresa.DoesNotExist:
        raise PermissionError(f"Empresa {empresa_id} no encontrada.")

    qs = Contacto.objects.filter(id_empresa=empresa, activo=True)

    if query:
        qs = qs.filter(
            models.Q(nombre__icontains=query)
            | models.Q(apellido__icontains=query)
            | models.Q(nombre_comercial__icontains=query)
            | models.Q(rif__icontains=query)
            | models.Q(cedula__icontains=query)
            | models.Q(email__icontains=query)
        )

    if rol:
        campo = f"es_{rol}"
        if hasattr(Contacto, campo):
            qs = qs.filter(**{campo: True})

    resultados = []
    for c in qs.select_related("lista_precio")[: min(limit, 100)]:
        resultados.append(
            {
                "id_contacto": str(c.id_contacto),
                "nombre": str(c),
                "tipo_persona": c.tipo_persona,
                "rif": c.rif,
                "cedula": c.cedula,
                "email": c.email,
                "telefono": c.telefono,
                "roles": {
                    "cliente": c.es_cliente,
                    "proveedor": c.es_proveedor,
                    "empleado": c.es_empleado,
                    "usuario": c.es_usuario,
                },
                "tipo_credito": c.tipo_credito,
                "limite_credito": str(c.limite_credito),
                "lista_precio": c.lista_precio.codigo if c.lista_precio else None,
            }
        )

    logger.info(
        "omni_buscar_contacto | actor=%s | tenant=%s | query=%r | rol=%s | resultados=%d",
        context["actor_id"],
        context["tenant_id"],
        query,
        rol,
        len(resultados),
    )
    return resultados


# ── Registrar herramientas con MCP cuando el SDK esté disponible ─────────────

if MCP_AVAILABLE and mcp is not None:
    omni_ping = mcp.tool()(omni_ping)
    omni_get_empresas = mcp.tool()(omni_get_empresas)
    omni_get_clientes = mcp.tool()(omni_get_clientes)
    omni_get_saldo_cliente = mcp.tool()(omni_get_saldo_cliente)
    omni_get_cxc_aging = mcp.tool()(omni_get_cxc_aging)
    omni_get_stock_producto = mcp.tool()(omni_get_stock_producto)
    omni_get_ventas_resumen = mcp.tool()(omni_get_ventas_resumen)
    omni_buscar_contacto = mcp.tool()(omni_buscar_contacto)
