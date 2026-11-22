"""
apps/finanzas/mcp.py — Herramientas MCP del módulo de Finanzas (ADR-003).

Herramientas expuestas:
  finanzas_get_pagos                   — lista pagos registrados de una empresa
  finanzas_get_saldo_caja              — saldo actual de una caja física
  finanzas_get_metodos_pago            — lista métodos de pago disponibles
  finanzas_pagos_terceros_pendientes   — pagos de terceros (Zelle) por gestionar
  finanzas_get_saldos_favor_contacto   — saldos a favor / anticipos de un contacto
  finanzas_conciliar_pago_multiple           — aplica un pago a 1..N documentos en lote atómico
  finanzas_revertir_asignacion_pago          — revierte una asignación activa con contra-asiento
  finanzas_listar_tipos_tasa                 — lista tipos de tasa globales y de la empresa
  finanzas_calcular_equivalencias_trimonetarias — calcula equivalencias Base/País(BCV)/Referencia
"""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

logger = logging.getLogger("omni.mcp.finanzas")

_SCOPE = "finanzas"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


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

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        limit = min(limit, 200)
        qs = Pago.objects.filter(
            id_empresa=empresa_id,
        ).select_related("id_metodo_pago", "id_moneda")
        if tipo_documento:
            qs = qs.filter(tipo_documento=tipo_documento)

        pagos = qs.order_by("-fecha_pago")[:limit]
        logger.info(
            "finanzas_get_pagos | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(pagos),
        )
        return [
            {
                "id_pago": str(p.id_pago),
                "monto": p.monto,  # BUG-NEW-2: Decimal, no float
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

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        try:
            caja = CajaFisica.objects.get(pk=caja_id, empresa_id=empresa_id)
        except CajaFisica.DoesNotExist:
            return {"error": f"Caja {caja_id} no encontrada."}

        logger.info(
            "finanzas_get_saldo_caja | actor=%s | tenant=%s | caja=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            caja_id,
        )

        # Obtener la sesión activa si existe
        sesion_activa = caja.sesiones.filter(fecha_cierre__isnull=True).first()
        saldo_apertura = sesion_activa.saldo_inicial if sesion_activa else Decimal("0")

        return {
            "caja_id": str(caja.id_caja_fisica),
            "nombre": caja.nombre,
            "activa": caja.activa,
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
    from apps.finanzas.cache import normalizar_empresa_uuid, obtener_metodos_pago_mcp  # noqa: PLC0415

    # finanzas_metodo_pago tiene null_visible=True: bajo rls_tenant_context ve filas globales (NULL) y del tenant.
    with _ctx(capability_token, f"{_SCOPE}:read") as ctx:
        tenant_uuid = normalizar_empresa_uuid(ctx["tenant_id"])
        if tenant_uuid is None:
            raise ValueError("tenant_id inválido en contexto MCP.")
        metodos = obtener_metodos_pago_mcp(tenant_uuid)
        logger.info(
            "finanzas_get_metodos_pago | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(metodos),
        )
        return metodos


def finanzas_pagos_terceros_pendientes(
    capability_token: str,
    empresa_id: str,
    limit: int = 50,
) -> list:
    """
    Lista los pagos de terceros (Zelle, §6.6 Capa B) que siguen abiertos:
    estado ``pendiente`` (sin abonar/reintegrar) o ``reintegro_pendiente``
    (CxC emitida, esperando que el proveedor devuelva el dinero).

    Scope requerido: ``finanzas:read``

    Args:
        capability_token: Token con scope ``finanzas:read``.
        empresa_id:       ID de la empresa.
        limit:            Máximo de resultados (default 50, máx 200).

    Returns:
        Lista con id, proveedor, monto, comision, moneda, referencia_zelle,
        fecha, estado y la CxC de reintegro si existe.
    """
    from apps.finanzas.models import PagoTercero  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        limit = min(limit, 200)
        pagos = (
            PagoTercero.objects.filter(
                id_empresa=empresa_id,
                estado__in=["pendiente", "reintegro_pendiente"],
                activo=True,
            )
            .select_related("id_proveedor", "id_moneda")
            .order_by("-fecha", "-fecha_creacion")[:limit]
        )
        logger.info(
            "finanzas_pagos_terceros_pendientes | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(pagos),
        )
        return [
            {
                "id_pago_tercero": str(p.id_pago_tercero),
                "proveedor": p.id_proveedor.razon_social if p.id_proveedor else "",
                "proveedor_id": str(p.id_proveedor_id) if p.id_proveedor_id else "",
                "monto": p.monto,  # Decimal, no float (R-CODE-4)
                "comision": p.comision if p.comision is not None else None,
                "moneda": p.id_moneda.codigo_iso if p.id_moneda else "",
                "referencia_zelle": p.referencia_zelle,
                "fecha": str(p.fecha),
                "estado": p.estado,
                "cxc_reintegro_id": str(p.id_cxc_reintegro_id) if p.id_cxc_reintegro_id else "",
            }
            for p in pagos
        ]


def _parse_decimal_mcp(valor: Any, campo: str) -> Decimal:
    if valor is None or isinstance(valor, bool):
        raise ValueError(f"El campo '{campo}' debe ser numérico.")
    try:
        dec = valor if isinstance(valor, Decimal) else Decimal(str(valor).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Valor numérico inválido para '{campo}': {valor!r}.") from exc
    if not dec.is_finite():
        raise ValueError(f"El valor de '{campo}' debe ser finito.")
    return dec


def finanzas_get_saldos_favor_contacto(
    capability_token: str,
    empresa_id: str,
    contacto_id: str,
    tipo_operacion: str = "",
) -> dict:
    """
    Consulta los saldos a favor / anticipos disponibles de un ``core.Contacto``.

    Scope requerido: ``finanzas:read``
    """
    from apps.core.models import Contacto, Empresa  # noqa: PLC0415
    from apps.finanzas.services_conciliacion_pagos import (  # noqa: PLC0415
        ConciliacionPagoError,
        saldo_a_favor_contacto,
    )

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        try:
            contacto_uuid = uuid.UUID(str(contacto_id))
        except (ValueError, TypeError):
            return {"error": f"contacto_id inválido: {contacto_id!r}."}

        empresa = Empresa.objects.filter(id_empresa=empresa_id, activo=True).first()
        if empresa is None:
            return {"error": "Empresa no encontrada o inactiva."}

        contacto = Contacto.objects.filter(pk=contacto_uuid, id_empresa=empresa).first()
        if contacto is None:
            return {"error": f"Contacto {contacto_id} no encontrado en la empresa."}

        tipo_op = tipo_operacion.strip() if tipo_operacion else None
        try:
            resumen = saldo_a_favor_contacto(empresa, contacto, tipo_operacion=tipo_op)
        except ConciliacionPagoError as exc:
            return {"error": str(exc)}

        pagos_serializados = [
            {
                **p,
                "fecha_pago": p["fecha_pago"].isoformat()
                if hasattr(p["fecha_pago"], "isoformat")
                else str(p["fecha_pago"]),
            }
            for p in resumen["pagos_con_saldo"]
        ]
        logger.info(
            "finanzas_get_saldos_favor_contacto | actor=%s | tenant=%s | contacto=%s | pagos=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            contacto_id,
            len(pagos_serializados),
        )
        return {
            "empresa_id": resumen["empresa_id"],
            "contacto_id": resumen["contacto_id"],
            "tipo_operacion": resumen["tipo_operacion"],
            "total_por_moneda": resumen["total_por_moneda"],
            "por_operacion": resumen["por_operacion"],
            "pagos_con_saldo": pagos_serializados,
        }


def finanzas_conciliar_pago_multiple(
    capability_token: str,
    empresa_id: str,
    pago_id: str,
    asignaciones: list[dict],
    descripcion: str = "",
) -> dict:
    """
    Aplica un ``Pago`` a 1..N facturas/obligaciones del mismo ``core.Contacto``.

    Scope requerido: ``finanzas:write``
    """
    from apps.finanzas.models import Pago  # noqa: PLC0415
    from apps.finanzas.services_conciliacion_pagos import (  # noqa: PLC0415
        ConciliacionPagoError,
        aplicar_pago_a_documentos,
        saldo_disponible_pago,
    )

    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_id) as ctx:
        try:
            pago_uuid = uuid.UUID(str(pago_id))
        except (ValueError, TypeError):
            return {"error": f"pago_id inválido: {pago_id!r}."}

        if not isinstance(asignaciones, list) or not asignaciones:
            return {"error": "Debe indicar una lista no vacía de asignaciones."}

        pago = (
            Pago.objects.select_related("id_empresa", "id_contacto", "id_moneda")
            .filter(pk=pago_uuid, id_empresa=empresa_id)
            .first()
        )
        if pago is None:
            return {"error": f"Pago {pago_id} no encontrado en la empresa."}

        items_parseados: list[dict[str, Any]] = []
        try:
            for idx, item in enumerate(asignaciones):
                if not isinstance(item, dict):
                    return {"error": f"El elemento {idx} de asignaciones debe ser un objeto."}
                normalizado = dict(item)
                normalizado["monto_asignado_pago"] = _parse_decimal_mcp(
                    item.get("monto_asignado_pago"),
                    "monto_asignado_pago",
                )
                for campo_opt in ("monto_asignado_documento", "tasa_aplicada", "tasa_original", "tasa_liquidacion"):
                    if item.get(campo_opt) not in (None, ""):
                        normalizado[campo_opt] = _parse_decimal_mcp(item.get(campo_opt), campo_opt)
                items_parseados.append(normalizado)
        except ValueError as exc:
            return {"error": str(exc)}

        try:
            creadas = aplicar_pago_a_documentos(
                pago,
                items_parseados,
                descripcion=descripcion,
            )
        except ConciliacionPagoError as exc:
            return {"error": str(exc)}

        saldo_restante = saldo_disponible_pago(pago)
        logger.info(
            "finanzas_conciliar_pago_multiple | actor=%s | tenant=%s | pago=%s | creadas=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            pago_id,
            len(creadas),
        )
        return {
            "pago_id": str(pago.pk),
            "asignaciones_creadas": [
                {
                    "id_asignacion": str(a.pk),
                    "tipo_documento": a.tipo_documento,
                    "id_documento": a.id_documento,
                    "monto_asignado_pago": a.monto_asignado_pago,
                    "monto_asignado_documento": a.monto_asignado_documento,
                    "diferencia_cambiaria": a.diferencia_cambiaria,
                    "tipo_diferencia": a.tipo_diferencia,
                    "estado": a.estado,
                }
                for a in creadas
            ],
            "saldo_disponible": saldo_restante,
        }


def finanzas_revertir_asignacion_pago(
    capability_token: str,
    empresa_id: str,
    asignacion_id: str,
    motivo: str | None = "",
) -> dict:
    """
    Revierte una ``AsignacionPago`` activa, restaura saldos y emite contra-asiento.

    Scope requerido: ``finanzas:write``
    """
    from apps.finanzas.models import AsignacionPago  # noqa: PLC0415
    from apps.finanzas.services_conciliacion_pagos import (  # noqa: PLC0415
        ConciliacionPagoError,
        revertir_asignacion_pago,
        saldo_disponible_pago,
    )

    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_id) as ctx:
        try:
            asig_uuid = uuid.UUID(str(asignacion_id))
        except (ValueError, TypeError):
            return {"error": f"asignacion_id inválido: {asignacion_id!r}."}

        asignacion = (
            AsignacionPago.objects.select_related("id_pago").filter(pk=asig_uuid, id_empresa=empresa_id).first()
        )
        if asignacion is None:
            return {"error": f"AsignacionPago {asignacion_id} no encontrada en la empresa."}

        try:
            revertida = revertir_asignacion_pago(asignacion, motivo=str(motivo or ""))
        except ConciliacionPagoError as exc:
            return {"error": str(exc)}

        saldo_pago = saldo_disponible_pago(revertida.id_pago)
        logger.info(
            "finanzas_revertir_asignacion_pago | actor=%s | tenant=%s | asignacion=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            asignacion_id,
        )
        return {
            "id_asignacion": str(revertida.pk),
            "estado": revertida.estado,
            "pago_id": str(revertida.id_pago_id),
            "saldo_disponible_pago": saldo_pago,
            "fecha_reversion": revertida.fecha_reversion.isoformat() if revertida.fecha_reversion else None,
            "motivo_reversion": revertida.motivo_reversion,
        }


def finanzas_listar_tipos_tasa(
    capability_token: str,
    empresa_id: str,
) -> list:
    """
    Lista los tipos de tasa de cambio activos visibles para la empresa (globales + propios).

    Scope requerido: ``finanzas:read``
    """
    from django.db.models import Q  # noqa: PLC0415

    from apps.finanzas.models import TipoTasaCambio  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        tipos = TipoTasaCambio.objects.filter(
            Q(id_empresa__isnull=True) | Q(id_empresa=empresa_id),
            activo=True,
        ).order_by("prioridad", "codigo")
        logger.info(
            "finanzas_listar_tipos_tasa | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(tipos),
        )
        return [
            {
                "id_tipo_tasa": str(t.id_tipo_tasa),
                "codigo": t.codigo,
                "nombre": t.nombre,
                "es_oficial_fiscal": t.es_oficial_fiscal,
                "es_global": t.id_empresa_id is None,
                "prioridad": t.prioridad,
            }
            for t in tipos
        ]


def _limpiar_texto_mcp(valor: Any, campo: str) -> str:
    texto = str(valor or "")
    if "\x00" in texto:
        raise ValueError(f"El parámetro '{campo}' contiene caracteres inválidos.")
    return texto.strip()


def _serializar_tasa_mcp(meta: dict | None) -> dict | None:
    if meta is None:
        return None
    fecha_tasa = meta.get("fecha_tasa")
    return {
        **meta,
        "fecha_tasa": (
            fecha_tasa.isoformat() if fecha_tasa is not None and hasattr(fecha_tasa, "isoformat") else fecha_tasa
        ),
    }


def finanzas_calcular_equivalencias_trimonetarias(
    capability_token: str,
    empresa_id: str,
    monto: Any,
    moneda_origen: str,
    fecha: str = "",
    codigo_tipo_tasa_base: str = "",
    codigo_tipo_tasa_referencia: str = "",
) -> dict:
    """
    Convierte un monto simultáneamente a Moneda Base, Moneda País (BCV) y Moneda Referencia.

    Scope requerido: ``finanzas:read``
    """
    from datetime import date  # noqa: PLC0415

    from apps.core.models import Empresa  # noqa: PLC0415
    from apps.finanzas.services import TasaCambioError  # noqa: PLC0415
    from apps.finanzas.services_trimonetario import calcular_equivalencias_trimonetarias  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        empresa = (
            Empresa.objects.select_related("id_moneda_base", "id_moneda_pais")
            .filter(id_empresa=empresa_id, activo=True)
            .first()
        )
        if empresa is None:
            return {"error": "Empresa no encontrada o inactiva."}

        try:
            monto_dec = _parse_decimal_mcp(monto, "monto")
            moneda_iso = _limpiar_texto_mcp(moneda_origen, "moneda_origen")
            tipo_base = _limpiar_texto_mcp(codigo_tipo_tasa_base, "codigo_tipo_tasa_base") or None
            tipo_ref = _limpiar_texto_mcp(codigo_tipo_tasa_referencia, "codigo_tipo_tasa_referencia") or None
            fecha_txt = _limpiar_texto_mcp(fecha, "fecha")
        except ValueError as exc:
            return {"error": str(exc)}

        fecha_obj = None
        if fecha_txt:
            try:
                fecha_obj = date.fromisoformat(fecha_txt)
            except ValueError:
                return {"error": "La fecha debe tener formato YYYY-MM-DD."}

        try:
            res = calcular_equivalencias_trimonetarias(
                monto_dec,
                moneda_iso,
                empresa=empresa,
                fecha=fecha_obj,
                codigo_tipo_tasa_base=tipo_base,
                codigo_tipo_tasa_referencia=tipo_ref,
            )
        except (TasaCambioError, ValueError) as exc:
            return {"error": str(exc)}

        logger.info(
            "finanzas_calcular_equivalencias_trimonetarias | actor=%s | tenant=%s | origen=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            res["moneda_origen_iso"],
        )
        return {
            "fecha": res["fecha"].isoformat(),
            "moneda_origen_iso": res["moneda_origen_iso"],
            "monto_origen": res["monto_origen"],
            "moneda_base_iso": res["moneda_base_iso"],
            "monto_base": res["monto_base"],
            "tasa_base": _serializar_tasa_mcp(res["tasa_base"]),
            "moneda_pais_iso": res["moneda_pais_iso"],
            "monto_pais_fiscal": res["monto_pais_fiscal"],
            "tasa_pais_fiscal": _serializar_tasa_mcp(res["tasa_pais_fiscal"]),
            "moneda_referencia_activa": res["moneda_referencia_activa"],
            "moneda_referencia_iso": res["moneda_referencia_iso"],
            "monto_referencia": res["monto_referencia"],
            "tasa_referencia": _serializar_tasa_mcp(res["tasa_referencia"]),
        }


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
    {
        "fn": finanzas_pagos_terceros_pendientes,
        "name": "finanzas_pagos_terceros_pendientes",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": finanzas_get_saldos_favor_contacto,
        "name": "finanzas_get_saldos_favor_contacto",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": finanzas_conciliar_pago_multiple,
        "name": "finanzas_conciliar_pago_multiple",
        "scope": f"{_SCOPE}:write",
    },
    {
        "fn": finanzas_revertir_asignacion_pago,
        "name": "finanzas_revertir_asignacion_pago",
        "scope": f"{_SCOPE}:write",
    },
    {
        "fn": finanzas_listar_tipos_tasa,
        "name": "finanzas_listar_tipos_tasa",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": finanzas_calcular_equivalencias_trimonetarias,
        "name": "finanzas_calcular_equivalencias_trimonetarias",
        "scope": f"{_SCOPE}:read",
    },
]
