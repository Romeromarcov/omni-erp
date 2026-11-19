"""Herramientas MCP de Tesorería — Extractos y saldos bancarios consolidados (R-CODE-7 / ADR-003)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("omni.mcp.tesoreria")

_SCOPE = "tesoreria"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


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

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
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

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
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


def tesoreria_listar_propuestas_conciliacion(
    capability_token: str,
    empresa_id: str,
    cuenta_id: str | None = None,
    estado: str | None = None,
    tipo: str | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Lista las propuestas de pre-conciliación bancaria de la empresa.

    Scope requerido: ``tesoreria:read``
    """
    from apps.tesoreria.models import PropuestaConciliacionBancaria  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
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
            PropuestaConciliacionBancaria.objects.filter(
                id_empresa=empresa, activo=True, id_movimiento_bancario__activo=True
            )
            .select_related("id_movimiento_bancario__id_cuenta_bancaria")
            .order_by(
                "-id_movimiento_bancario__fecha_mov",
                "-id_movimiento_bancario__orden_en_archivo",
                "-generada_en",
            )
        )
        if cuenta_id:
            qs = qs.filter(id_movimiento_bancario__id_cuenta_bancaria_id=uuid.UUID(str(cuenta_id)))
        if estado:
            qs = qs.filter(estado=str(estado).replace("\x00", "").strip().upper())
        if tipo:
            qs = qs.filter(tipo=str(tipo).replace("\x00", "").strip().upper())

        items = list(qs[:tope])
        logger.info(
            "tesoreria_listar_propuestas_conciliacion | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(items),
        )
        return [
            {
                "id": str(p.id),
                "movimiento_id": str(p.id_movimiento_bancario_id),
                "cuenta_id": str(p.id_movimiento_bancario.id_cuenta_bancaria_id),
                "nombre_banco": p.id_movimiento_bancario.id_cuenta_bancaria.nombre_banco,
                "fecha": p.id_movimiento_bancario.fecha_mov.isoformat(),
                "tipo_movimiento": p.id_movimiento_bancario.tipo,
                "monto": f"{p.id_movimiento_bancario.monto:.2f}",
                "referencia": p.id_movimiento_bancario.referencia,
                "descripcion": p.id_movimiento_bancario.descripcion,
                "tipo_propuesta": p.tipo,
                "regla": p.regla,
                "motivo": p.motivo,
                "fuente_pago": p.fuente_pago,
                "id_pago_nativo": str(p.id_pago_nativo_id) if p.id_pago_nativo_id else None,
                "pago_externo_id": p.pago_externo_id or None,
                "pago_nombre": p.pago_nombre,
                "pago_socio": p.pago_socio,
                "cuenta_contable_codigo": p.cuenta_contable_codigo,
                "puntaje": p.puntaje,
                "estado": p.estado,
            }
            for p in items
        ]


def tesoreria_generar_propuestas_conciliacion(
    capability_token: str,
    empresa_id: str,
    cuenta_id: str,
    desde: str | None = None,
    hasta: str | None = None,
    incluir_odoo: bool | None = None,
) -> dict[str, Any]:
    """Ejecuta el motor determinístico R1/R2/R3 de pre-conciliación para una cuenta bancaria.

    Scope requerido: ``tesoreria:write``
    """
    from datetime import date  # noqa: PLC0415

    from apps.finanzas.models import CuentaBancariaEmpresa  # noqa: PLC0415
    from apps.tesoreria.preconciliacion import (  # noqa: PLC0415
        PreconciliacionError,
        generar_propuestas_conciliacion,
    )

    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_id) as ctx:
        try:
            cuenta_uuid = uuid.UUID(str(cuenta_id))
        except (ValueError, TypeError) as exc:
            raise ValueError("cuenta_id no es un UUID válido.") from exc

        fecha_desde = None
        fecha_hasta = None
        try:
            if desde:
                fecha_desde = date.fromisoformat(str(desde).strip())
            if hasta:
                fecha_hasta = date.fromisoformat(str(hasta).strip())
        except ValueError as exc:
            raise ValueError("Las fechas desde/hasta deben usar formato ISO YYYY-MM-DD.") from exc

        empresa = _empresa_activa(ctx["empresa_id"])
        cuenta = (
            CuentaBancariaEmpresa.objects.select_related("id_empresa", "id_moneda")
            .filter(pk=cuenta_uuid, id_empresa=empresa, activo=True)
            .first()
        )
        if cuenta is None:
            raise ValueError("Cuenta bancaria no encontrada en esta empresa.")

        try:
            resumen = generar_propuestas_conciliacion(
                empresa=empresa,
                cuenta_bancaria=cuenta,
                desde=fecha_desde,
                hasta=fecha_hasta,
                incluir_odoo=incluir_odoo,
            )
        except PreconciliacionError as exc:
            raise ValueError(str(exc)) from exc

        logger.info(
            "tesoreria_generar_propuestas_conciliacion | actor=%s | tenant=%s | nuevas=%d | actualizadas=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            resumen["nuevas"],
            resumen["actualizadas"],
        )
        return resumen


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
    {
        "fn": tesoreria_listar_propuestas_conciliacion,
        "name": "tesoreria_listar_propuestas_conciliacion",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": tesoreria_generar_propuestas_conciliacion,
        "name": "tesoreria_generar_propuestas_conciliacion",
        "scope": f"{_SCOPE}:write",
    },
]
