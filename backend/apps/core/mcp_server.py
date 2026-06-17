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

Herramientas disponibles (v1):
  Núcleo / CRM
  - omni_ping              : health check
  - omni_get_empresas      : lista empresas del tenant
  - omni_get_clientes      : lista clientes de una empresa
  - omni_buscar_cliente    : busca clientes por nombre, RIF o email
  - omni_buscar_contacto   : busca contactos unificados

  CxC
  - omni_get_saldo_cliente : saldo CxC de un cliente específico
  - omni_get_cxc_aging     : aging de saldos por cobrar

  Inventario
  - omni_get_stock_producto              : stock disponible de un producto
  - omni_registrar_movimiento_inventario : registra ENTRADA / SALIDA / TRANSFERENCIA

  Ventas
  - omni_get_ventas_resumen: resumen de ventas (pedidos aprobados)
  - omni_crear_pedido      : crea un pedido de venta
  - omni_get_pedidos       : lista pedidos de una empresa

  Fiscal
  - omni_get_correlativo_fiscal: siguiente número correlativo fiscal
"""


import logging
import os
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

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

def _resolve_token(capability_token: str) -> Optional[Dict[str, Any]]:
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

    # SEC-NEW-4: el comodín '*' solo es efectivo para tokens de sistema/superusuario
    # (CapabilityToken.comodin_autorizado). Un token de empresa con scopes=["*"]
    # auto-otorgado NO debe conceder acceso total; se filtra aquí, en el único punto
    # de resolución, para que _require_scope siga siendo trivial.
    scopes = list(token_obj.scopes or [])
    if "*" in scopes and not token_obj.comodin_autorizado:
        scopes = [s for s in scopes if s != "*"]

    return {
        "tenant_id": str(token_obj.empresa.id_empresa),
        "empresa_id": str(token_obj.empresa.id_empresa),
        "actor_id": f"mcp-token:{str(token_obj.token)[:8]}",
        "scopes": scopes,
    }


def _require_scope(context: Optional[Dict[str, Any]], scope: str) -> None:
    """Lanza PermissionError si el contexto no tiene el scope requerido."""
    if context is None:
        raise PermissionError("Token de capacidad inválido o expirado.")
    if scope not in context["scopes"] and "*" not in context["scopes"]:
        raise PermissionError(f"El token no tiene el scope requerido: {scope}")


# ── Herramientas MCP (definidas a nivel de módulo para ser importables en tests) ─

def omni_ping(capability_token: str) -> dict:
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


def omni_get_empresas(capability_token: str) -> list:
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
    ).values("id_empresa", "nombre_comercial", "identificador_fiscal", "activo")

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
) -> list:
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
) -> dict:
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
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, "cxc:read")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    # CuentaPorCobrar NO tiene campo `saldo_pendiente`: el saldo se calcula como
    # monto - abonos (igual que calcular_aging). Estados en minúscula como en el
    # modelo (antes filtraba "PENDIENTE"/"PARCIAL" y agregaba campos inexistentes
    # `saldo_pendiente`/`id_cxc` → FieldError en cada llamada).
    cxcs = list(
        CuentaPorCobrar.objects.filter(
            empresa_id=empresa_id,
            cliente_id=cliente_id,
            estado__in=["pendiente", "parcial", "vencida"],
        ).prefetch_related("abonos")
    )
    total = Decimal("0")
    for cxc in cxcs:
        abonado = sum((a.monto for a in cxc.abonos.all()), Decimal("0"))
        total += cxc.monto - abonado

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
        "total_pendiente": total,  # Decimal (R-CODE-4)
        "cantidad_facturas": len(cxcs),
        "moneda_base": "USD",
    }


def omni_get_cxc_aging(
    capability_token: str,
    empresa_id: str,
) -> dict:
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
        return {"count": b["count"], "total": b["total"]}  # BUG-NEW-2

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
        "total_general": resultado["total_general"],  # BUG-NEW-2
    }


def omni_get_stock_producto(
    capability_token: str,
    empresa_id: str,
    producto_id: str,
    almacen_id: str = "",
) -> list:
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
) -> dict:
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

    # BUG-NEW-2: montos como Decimal (no float) para no perder precisión.
    total = totales["total"] or Decimal("0")
    promedio = totales["promedio"] or Decimal("0")

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


def omni_crear_pedido(
    capability_token: str,
    empresa_id: str,
    cliente_id: str,
    productos: list,
) -> dict:
    """
    Crea un pedido de venta.

    Scope requerido: `ventas:write`

    Args:
        capability_token: Token con scope `ventas:write`.
        empresa_id:       ID de la empresa.
        cliente_id:       ID del cliente.
        productos:        Lista de líneas: [{"id_producto": "uuid", "cantidad": 1, "precio_unitario": "100.00"}]

    Returns:
        dict con numero_pedido, id_pedido, estado.
    """
    from decimal import Decimal  # noqa: PLC0415

    from django.db import transaction  # noqa: PLC0415
    from django.utils import timezone  # noqa: PLC0415

    from apps.ventas.models import DetallePedido, Pedido  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, "ventas:write")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    if not productos:
        raise ValueError("Se requiere al menos un producto.")

    try:
        with transaction.atomic():
            # Generar número de pedido: PED-YYYYMMDD-HHMMSS
            ts = timezone.now().strftime("%Y%m%d-%H%M%S")
            numero_pedido = f"PED-{ts}"

            pedido = Pedido.objects.create(
                id_empresa_id=empresa_id,
                id_cliente_id=cliente_id,
                numero_pedido=numero_pedido,
                fecha_pedido=timezone.now().date(),
                estado="PENDIENTE",
            )

            for linea in productos:
                cantidad = Decimal(str(linea["cantidad"]))
                precio_unitario = Decimal(str(linea["precio_unitario"]))
                DetallePedido.objects.create(
                    id_pedido=pedido,
                    id_producto_id=linea["id_producto"],
                    cantidad=cantidad,
                    precio_unitario=precio_unitario,
                    subtotal=cantidad * precio_unitario,
                )

        logger.info(
            "omni_crear_pedido | actor=%s | tenant=%s | pedido=%s | lineas=%d",
            context["actor_id"],
            context["tenant_id"],
            numero_pedido,
            len(productos),
        )
        return {
            "id_pedido": str(pedido.id_pedido),
            "numero_pedido": pedido.numero_pedido,
            "estado": pedido.estado,
            "cantidad_lineas": len(productos),
        }
    except Exception as exc:
        logger.exception("omni_crear_pedido | error: %s", exc)
        return {"error": str(exc)}


def omni_get_pedidos(
    capability_token: str,
    empresa_id: str,
    estado: str = "",
    limit: int = 20,
) -> list:
    """
    Retorna pedidos de una empresa, opcionalmente filtrados por estado.

    Scope requerido: `ventas:read`

    Args:
        capability_token: Token con scope `ventas:read`.
        empresa_id:       ID de la empresa.
        estado:           Filtrar por estado (PENDIENTE, ENVIADO, APROBADO, RECHAZADO, ANULADO). Vacío = todos.
        limit:            Máximo de resultados (default 20, máx 100).

    Returns:
        Lista de pedidos con id, numero, cliente, fecha, estado.
    """
    from apps.ventas.models import Pedido  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, "ventas:read")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    try:
        limit = min(limit, 100)
        qs = Pedido.objects.filter(id_empresa=empresa_id, activo=True).select_related("id_cliente")
        if estado:
            qs = qs.filter(estado=estado)

        pedidos = qs.order_by("-fecha_pedido")[:limit]

        logger.info(
            "omni_get_pedidos | actor=%s | tenant=%s | empresa=%s | estado=%s | count=%d",
            context["actor_id"],
            context["tenant_id"],
            empresa_id,
            estado or "todos",
            len(pedidos),
        )
        return [
            {
                "id_pedido": str(p.id_pedido),
                "numero_pedido": p.numero_pedido,
                "cliente": p.id_cliente.razon_social,
                "fecha_pedido": str(p.fecha_pedido),
                "estado": p.estado,
            }
            for p in pedidos
        ]
    except Exception as exc:
        logger.exception("omni_get_pedidos | error: %s", exc)
        return [{"error": str(exc)}]


def omni_registrar_movimiento_inventario(
    capability_token: str,
    empresa_id: str,
    producto_id: str,
    tipo: str,
    cantidad: str,
    almacen_destino_id: str = "",
    almacen_origen_id: str = "",
) -> dict:
    """
    Registra un movimiento de inventario.

    Scope requerido: `inventario:write`

    Args:
        capability_token:   Token con scope `inventario:write`.
        empresa_id:         ID de la empresa.
        producto_id:        ID del producto.
        tipo:               Tipo de movimiento: ENTRADA | SALIDA | TRANSFERENCIA.
        cantidad:           Cantidad del movimiento (string decimal).
        almacen_destino_id: ID del almacén destino (requerido para ENTRADA y TRANSFERENCIA).
        almacen_origen_id:  ID del almacén origen (requerido para SALIDA y TRANSFERENCIA).

    Returns:
        dict con id_movimiento, tipo, cantidad.
    """
    from decimal import Decimal  # noqa: PLC0415

    from django.utils import timezone  # noqa: PLC0415

    from apps.inventario.models import MovimientoInventario  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, "inventario:write")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    TIPOS_VALIDOS = {"ENTRADA", "SALIDA", "TRANSFERENCIA"}
    if tipo not in TIPOS_VALIDOS:
        return {"error": f"tipo '{tipo}' inválido. Válidos: {sorted(TIPOS_VALIDOS)}"}

    # M-SEC-10: validar que el actor del token MCP sea un UUID de usuario real
    # antes de usarlo como FK (evita IntegrityError opaco / inyección de FK).
    import uuid as _uuid

    from apps.core.models import Usuarios  # noqa: PLC0415

    actor_raw = context["actor_id"].replace("mcp-token:", "")
    try:
        _uuid.UUID(str(actor_raw))
        actor_valido = Usuarios.objects.filter(pk=actor_raw).exists()
    except (ValueError, TypeError):
        actor_valido = False
    if not actor_valido:
        return {"error": "actor_id del token MCP no corresponde a un usuario válido."}

    try:
        movimiento = MovimientoInventario.objects.create(
            id_empresa_id=empresa_id,
            fecha_hora_movimiento=timezone.now(),
            tipo_movimiento=tipo,
            id_producto_id=producto_id,
            cantidad=Decimal(cantidad),
            id_almacen_origen_id=almacen_origen_id or None,
            id_almacen_destino_id=almacen_destino_id or None,
            id_usuario_registro_id=actor_raw,
        )

        logger.info(
            "omni_registrar_movimiento_inventario | actor=%s | tenant=%s | tipo=%s | producto=%s | cantidad=%s",
            context["actor_id"],
            context["tenant_id"],
            tipo,
            producto_id,
            cantidad,
        )
        return {
            "id_movimiento": str(movimiento.id_movimiento_inventario),
            "tipo": movimiento.tipo_movimiento,
            "cantidad": str(movimiento.cantidad),
            "empresa_id": empresa_id,
        }
    except Exception as exc:
        logger.exception("omni_registrar_movimiento_inventario | error: %s", exc)
        return {"error": str(exc)}


def omni_get_correlativo_fiscal(
    capability_token: str,
    empresa_id: str,
    tipo_documento: str,
) -> dict:
    """
    Retorna el siguiente número correlativo fiscal para un tipo de documento.

    Scope requerido: `fiscal:read`

    Args:
        capability_token: Token con scope `fiscal:read`.
        empresa_id:       ID de la empresa.
        tipo_documento:   FACTURA | NOTA_CREDITO | NOTA_DEBITO

    Returns:
        dict con tipo_documento, numero_actual, siguiente_numero, prefijo, numero_formateado.
    """
    from apps.fiscal.models import NumeroCorrelativo  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, "fiscal:read")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    TIPOS_VALIDOS = {"FACTURA", "NOTA_CREDITO", "NOTA_DEBITO"}
    if tipo_documento not in TIPOS_VALIDOS:
        return {"error": f"tipo_documento '{tipo_documento}' inválido. Válidos: {sorted(TIPOS_VALIDOS)}"}

    try:
        correlativo = NumeroCorrelativo.objects.get(
            id_empresa=empresa_id,
            tipo=tipo_documento,
        )
        siguiente = correlativo.numero_actual + 1
        formateado = f"{correlativo.prefijo}{siguiente:0{correlativo.digitos}d}"

        logger.info(
            "omni_get_correlativo_fiscal | actor=%s | tenant=%s | tipo=%s | siguiente=%d",
            context["actor_id"],
            context["tenant_id"],
            tipo_documento,
            siguiente,
        )
        return {
            "tipo_documento": tipo_documento,
            "empresa_id": empresa_id,
            "numero_actual": correlativo.numero_actual,
            "siguiente_numero": siguiente,
            "prefijo": correlativo.prefijo,
            "numero_formateado": formateado,
        }
    except NumeroCorrelativo.DoesNotExist:
        return {
            "error": f"No existe configuración de correlativo para tipo '{tipo_documento}' en la empresa {empresa_id}."
        }
    except Exception as exc:
        logger.exception("omni_get_correlativo_fiscal | error: %s", exc)
        return {"error": str(exc)}


def omni_buscar_cliente(
    capability_token: str,
    empresa_id: str,
    termino: str,
) -> list:
    """
    Busca clientes por nombre, RIF o email.

    Scope requerido: `crm:read`

    Args:
        capability_token: Token con scope `crm:read`.
        empresa_id:       ID de la empresa.
        termino:          Texto a buscar en razon_social, nombre_comercial, rif o email.

    Returns:
        Lista de clientes coincidentes.
    """
    from django.db.models import Q  # noqa: PLC0415

    from apps.crm.models import Cliente  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, "crm:read")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    try:
        qs = Cliente.objects.filter(
            id_empresa=empresa_id,
            activo=True,
        ).filter(
            Q(razon_social__icontains=termino)
            | Q(nombre_comercial__icontains=termino)
            | Q(rif__icontains=termino)
            | Q(email__icontains=termino)
        )[:50]

        logger.info(
            "omni_buscar_cliente | actor=%s | tenant=%s | termino=%r | count=%d",
            context["actor_id"],
            context["tenant_id"],
            termino,
            len(qs),
        )
        return [
            {
                "id_cliente": str(c.id_cliente),
                "razon_social": c.razon_social,
                "nombre_comercial": c.nombre_comercial or "",
                "rif": c.rif,
                "email": c.email or "",
                "telefono": c.telefono or "",
                "tipo_cliente": c.tipo_cliente,
            }
            for c in qs
        ]
    except Exception as exc:
        logger.exception("omni_buscar_cliente | error: %s", exc)
        return [{"error": str(exc)}]


def omni_cxc_get_cartera_vencida(
    capability_token: str,
    empresa_id: str,
    top_n: int = 10,
) -> list:
    """
    Obtiene la cartera vencida priorizada por score de cobrabilidad.

    Scope requerido: `cxc:read`

    Args:
        capability_token: Token con scope `cxc:read`.
        empresa_id:       ID de la empresa (debe coincidir con el tenant).
        top_n:            Número máximo de resultados (default 10, máx 50).

    Returns:
        Lista de partidas vencidas ordenadas por score DESC.
    """
    context = _resolve_token(capability_token)
    _require_scope(context, "cxc:read")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    from apps.core.models import Empresa  # noqa: PLC0415
    from apps.cuentas_por_cobrar.services_cartera_provider import get_cartera_provider  # noqa: PLC0415
    from apps.cuentas_por_cobrar.services_scoring import priorizar  # noqa: PLC0415

    top_n = min(top_n, 50)

    empresa = Empresa.objects.get(pk=empresa_id)
    provider = get_cartera_provider(empresa)
    partidas = provider.get_partidas(solo_vencidas=True)
    resultado = priorizar(partidas)[:top_n]

    logger.info(
        "omni_cxc_get_cartera_vencida | actor=%s | tenant=%s | count=%d",
        context["actor_id"], context["tenant_id"], len(resultado),
    )
    return resultado


def omni_cxc_get_aging_summary(
    capability_token: str,
    empresa_id: str,
) -> dict:
    """
    Resumen de aging de cartera por bucket (con cache 15 min).

    Scope requerido: `cxc:read`

    Returns:
        Dict con buckets: al_dia / 1_30 / 31_60 / 61_90 / mas_90
    """
    context = _resolve_token(capability_token)
    _require_scope(context, "cxc:read")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    from django.core.cache import cache  # noqa: PLC0415
    from apps.core.models import Empresa  # noqa: PLC0415
    from apps.cuentas_por_cobrar.services_cartera_provider import get_cartera_provider  # noqa: PLC0415
    from apps.cuentas_por_cobrar.services_aging import calcular_aging  # noqa: PLC0415

    cache_key = f"cxc:aging:{empresa_id}"
    resumen = cache.get(cache_key)

    if not resumen:
        empresa = Empresa.objects.get(pk=empresa_id)
        provider = get_cartera_provider(empresa)
        partidas = provider.get_partidas()
        resumen = calcular_aging(partidas)
        cache.set(cache_key, resumen, timeout=900)

    logger.info(
        "omni_cxc_get_aging_summary | actor=%s | tenant=%s",
        context["actor_id"], context["tenant_id"],
    )
    return resumen


def omni_cxc_get_tasa_cambio_hoy(
    capability_token: str,
    tipo_tasa: str = "OFICIAL_BCV",
) -> dict:
    """
    Obtiene la tasa de cambio USD/VES del día.

    Scope requerido: `finanzas:read`

    Args:
        capability_token: Token con scope `finanzas:read`.
        tipo_tasa:        'OFICIAL_BCV' | 'PROMEDIO_MERCADO' (default OFICIAL_BCV)

    Returns:
        dict con fecha, tipo_tasa, valor_tasa o error si no hay tasa hoy.
    """
    context = _resolve_token(capability_token)
    _require_scope(context, "finanzas:read")
    assert context is not None  # noqa: S101

    from datetime import date  # noqa: PLC0415
    from apps.finanzas.models import TasaCambio  # noqa: PLC0415

    tasa = (
        TasaCambio.objects.filter(
            fecha_tasa=date.today(),
            tipo_tasa=tipo_tasa,
            id_moneda_origen__codigo_iso="USD",
            id_moneda_destino__codigo_iso="VES",
        )
        .order_by("-fecha_creacion")
        .first()
    )

    if tasa is None:
        return {
            "error": f"No hay tasa {tipo_tasa} disponible para hoy ({date.today()})",
            "fecha": str(date.today()),
            "tipo_tasa": tipo_tasa,
            "valor_tasa": None,
        }

    logger.info(
        "omni_cxc_get_tasa_cambio_hoy | actor=%s | tipo=%s | tasa=%s",
        context["actor_id"], tipo_tasa, tasa.valor_tasa,
    )
    return {
        "fecha": str(tasa.fecha_tasa),
        "tipo_tasa": tasa.tipo_tasa,
        "valor_tasa": str(tasa.valor_tasa),
    }


def omni_cxc_get_acuerdos_vigentes(
    capability_token: str,
    empresa_id: str,
    cliente_id: str,
) -> list:
    """
    Obtiene los acuerdos de pago vigentes de un cliente.

    Scope requerido: `cxc:read`

    Returns:
        Lista de acuerdos con cuotas pendientes.
    """
    context = _resolve_token(capability_token)
    _require_scope(context, "cxc:read")
    assert context is not None  # noqa: S101

    if empresa_id != context["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    from apps.cxc.models import AcuerdoPago  # noqa: PLC0415

    acuerdos = AcuerdoPago.objects.filter(
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        estado="vigente",
        deleted_at__isnull=True,
    ).prefetch_related("cuotas")

    resultado = []
    for a in acuerdos:
        pendientes = a.cuotas.filter(estado__in=["pendiente", "vencido"]).count()
        resultado.append({
            "id": str(a.pk),
            "monto_total": str(a.monto_total),
            "periodicidad": a.periodicidad,
            "estado": a.estado,
            "fecha_inicio": str(a.fecha_inicio),
            "cuotas_pendientes": pendientes,
            "moneda": a.moneda_codigo,
        })

    logger.info(
        "omni_cxc_get_acuerdos_vigentes | actor=%s | cliente=%s | count=%d",
        context["actor_id"], cliente_id, len(resultado),
    )
    return resultado


def omni_buscar_contacto(
    capability_token: str,
    empresa_id: str,
    query: str = "",
    rol: str = "",
    limit: int = 20,
) -> list:
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

    if str(empresa_id) != context["empresa_id"]:
        raise PermissionError("El token no pertenece a la empresa solicitada.")

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
    # ── Herramientas extendidas (v1) ──────────────────────────────────────────
    omni_crear_pedido = mcp.tool()(omni_crear_pedido)
    omni_get_pedidos = mcp.tool()(omni_get_pedidos)
    omni_registrar_movimiento_inventario = mcp.tool()(omni_registrar_movimiento_inventario)
    omni_get_correlativo_fiscal = mcp.tool()(omni_get_correlativo_fiscal)
    omni_buscar_cliente = mcp.tool()(omni_buscar_cliente)
    # ── Herramientas CxC cobranza (v2) ───────────────────────────────────────
    omni_cxc_get_cartera_vencida = mcp.tool()(omni_cxc_get_cartera_vencida)
    omni_cxc_get_aging_summary = mcp.tool()(omni_cxc_get_aging_summary)
    omni_cxc_get_tasa_cambio_hoy = mcp.tool()(omni_cxc_get_tasa_cambio_hoy)
    omni_cxc_get_acuerdos_vigentes = mcp.tool()(omni_cxc_get_acuerdos_vigentes)


# ── Auto-discovery: registrar herramientas de módulos (MCP_AGENT_CAPABILITIES) ─
#
# Cualquier módulo apps.<modulo>.mcp que exporte MCP_TOOLS = [{"fn": ..., "name": ..., "scope": ...}]
# queda registrado aquí automáticamente.
#
# Para añadir un módulo al servidor MCP, agregar su ruta a MCP_MODULE_PATHS
# en settings.py como parte de MCP_AGENT_CAPABILITIES["module_paths"].

_MCP_DEFAULT_MODULE_PATHS = [
    "apps.ventas.mcp",
    "apps.inventario.mcp",
    "apps.finanzas.mcp",
    "apps.manufactura.mcp",
    "apps.nomina.mcp",
    "apps.fiscal.mcp",
    "apps.despacho.mcp",
]


def _autodiscover_module_tools(module_paths: Optional[List[str]] = None) -> dict:
    """
    Importa los módulos MCP por-módulo y registra sus herramientas en el servidor.

    Returns:
        dict mapping name → fn para todas las herramientas descubiertas.
    """
    import importlib  # noqa: PLC0415

    paths = module_paths or _MCP_DEFAULT_MODULE_PATHS
    discovered: Dict[str, Any] = {}

    for module_path in paths:
        try:
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            logger.warning("mcp_autodiscover: no se pudo importar %s: %s", module_path, exc)
            continue

        tools: List[Dict[str, Any]] = getattr(mod, "MCP_TOOLS", [])
        for tool_def in tools:
            fn = tool_def["fn"]
            name = tool_def["name"]
            discovered[name] = fn
            if MCP_AVAILABLE and mcp is not None:
                try:
                    mcp.tool()(fn)
                    logger.debug("mcp_autodiscover: registrado %s desde %s", name, module_path)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "mcp_autodiscover: error registrando %s desde %s: %s",
                        name, module_path, exc,
                    )

    logger.info("mcp_autodiscover: %d herramientas adicionales registradas", len(discovered))
    return discovered


# Ejecutar auto-discovery al importar el módulo
_DISCOVERED_TOOLS: Dict[str, Any] = _autodiscover_module_tools()
