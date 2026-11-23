"""Herramientas MCP de Contabilidad — Reportes financieros canónicos (PR-14 / ADR-003).

Herramientas expuestas (scope ``contabilidad:read``):
  - ``contabilidad_balance_comprobacion``
  - ``contabilidad_estado_resultados``
  - ``contabilidad_balance_general``
  - ``contabilidad_libro_mayor_auxiliar``
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.utils import timezone

if TYPE_CHECKING:
    from apps.core.models import Empresa

logger = logging.getLogger("omni.mcp.contabilidad")

_SCOPE = "contabilidad:read"
_FECHA_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def _serializar_salida(valor: Any) -> Any:
    """Serializa ``Decimal`` a ``str`` (R-CODE-4, cero floats) de forma recursiva."""
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {k: _serializar_salida(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_serializar_salida(item) for item in valor]
    return valor


def _parse_uuid_mcp(raw: str | None, campo: str) -> uuid.UUID | None:
    if raw is None or not str(raw).strip():
        return None
    limpio = str(raw).strip()
    if "\x00" in limpio:
        raise ValueError(f"El parámetro '{campo}' contiene caracteres inválidos.")
    try:
        return uuid.UUID(limpio)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"El parámetro '{campo}' no es un UUID válido.") from exc


def _parse_fecha_mcp(raw: str | None, campo: str) -> date | None:
    if raw is None or not str(raw).strip():
        return None
    limpio = str(raw).strip()
    if "\x00" in limpio or not _FECHA_ISO_RE.match(limpio):
        raise ValueError(f"Fecha inválida para '{campo}'. Use formato YYYY-MM-DD.")
    try:
        return date.fromisoformat(limpio)
    except ValueError as exc:
        raise ValueError(f"Fecha inválida para '{campo}'.") from exc


def _empresa_activa(empresa_id: str) -> Empresa:
    from apps.core.models import Empresa  # noqa: PLC0415

    empresa_uuid = _parse_uuid_mcp(empresa_id, "empresa_id")
    if empresa_uuid is None:
        raise ValueError("empresa_id es requerido.")
    empresa = Empresa.objects.filter(id_empresa=empresa_uuid, activo=True).first()
    if empresa is None:
        raise ValueError("Empresa no encontrada o inactiva.")
    return empresa


def contabilidad_balance_comprobacion(
    capability_token: str,
    empresa_id: str,
    fecha_desde: str = "",
    fecha_hasta: str = "",
    id_diario: str = "",
    incluir_equivalentes_usd: bool = False,
    ambito: str = "CONSOLIDADO",
    moneda: str = "BASE",
    id_centro_costo: str = "",
) -> dict[str, Any]:
    """Consulta el Balance de Comprobación canónico de la empresa.

    Scope requerido: ``contabilidad:read``
    """
    from apps.contabilidad.services_reportes import (  # noqa: PLC0415
        ReporteContableError,
        generar_balance_comprobacion,
    )

    with _ctx(capability_token, _SCOPE, empresa_id=empresa_id) as ctx:
        try:
            empresa = _empresa_activa(ctx["empresa_id"])
            f_desde = _parse_fecha_mcp(fecha_desde, "fecha_desde")
            f_hasta = _parse_fecha_mcp(fecha_hasta, "fecha_hasta")
            diario_uuid = _parse_uuid_mcp(id_diario, "id_diario")
            centro_uuid = _parse_uuid_mcp(id_centro_costo, "id_centro_costo")
            reporte = generar_balance_comprobacion(
                empresa,
                fecha_desde=f_desde,
                fecha_hasta=f_hasta,
                id_diario=diario_uuid,
                incluir_equivalentes_usd=bool(incluir_equivalentes_usd),
                ambito=ambito,
                moneda=moneda,
                id_centro_costo=centro_uuid,
            )
        except (ValueError, ReporteContableError) as exc:
            return {"error": str(exc)}

        logger.info(
            "contabilidad_balance_comprobacion | actor=%s | tenant=%s | cuentas=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(reporte["cuentas"]),
        )
        return _serializar_salida(reporte)  # type: ignore[no-any-return]


def contabilidad_estado_resultados(
    capability_token: str,
    empresa_id: str,
    fecha_desde: str = "",
    fecha_hasta: str = "",
    incluir_equivalentes_usd: bool = False,
    ambito: str = "CONSOLIDADO",
    moneda: str = "BASE",
    id_centro_costo: str = "",
) -> dict[str, Any]:
    """Consulta el Estado de Resultados (P&L) excluyendo asientos de cierre anual.

    Scope requerido: ``contabilidad:read``
    """
    from apps.contabilidad.services_reportes import (  # noqa: PLC0415
        ReporteContableError,
        generar_estado_resultados,
    )

    with _ctx(capability_token, _SCOPE, empresa_id=empresa_id) as ctx:
        try:
            empresa = _empresa_activa(ctx["empresa_id"])
            hoy = timezone.localdate()
            f_hasta = _parse_fecha_mcp(fecha_hasta, "fecha_hasta") or hoy
            f_desde = _parse_fecha_mcp(fecha_desde, "fecha_desde") or f_hasta.replace(month=1, day=1)
            centro_uuid = _parse_uuid_mcp(id_centro_costo, "id_centro_costo")
            reporte = generar_estado_resultados(
                empresa,
                fecha_desde=f_desde,
                fecha_hasta=f_hasta,
                incluir_equivalentes_usd=bool(incluir_equivalentes_usd),
                ambito=ambito,
                moneda=moneda,
                id_centro_costo=centro_uuid,
            )
        except (ValueError, ReporteContableError) as exc:
            return {"error": str(exc)}

        logger.info(
            "contabilidad_estado_resultados | actor=%s | tenant=%s | resultado=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            reporte["resultado_neto"],
        )
        return _serializar_salida(reporte)  # type: ignore[no-any-return]


def contabilidad_balance_general(
    capability_token: str,
    empresa_id: str,
    fecha_corte: str = "",
    incluir_equivalentes_usd: bool = False,
    ambito: str = "CONSOLIDADO",
    moneda: str = "BASE",
    id_centro_costo: str = "",
) -> dict[str, Any]:
    """Consulta el Balance General acumulado hasta ``fecha_corte`` con verificación de ecuación patrimonial.

    Scope requerido: ``contabilidad:read``
    """
    from apps.contabilidad.services_reportes import (  # noqa: PLC0415
        ReporteContableError,
        generar_balance_general,
    )

    with _ctx(capability_token, _SCOPE, empresa_id=empresa_id) as ctx:
        try:
            empresa = _empresa_activa(ctx["empresa_id"])
            f_corte = _parse_fecha_mcp(fecha_corte, "fecha_corte") or timezone.localdate()
            centro_uuid = _parse_uuid_mcp(id_centro_costo, "id_centro_costo")
            reporte = generar_balance_general(
                empresa,
                fecha_corte=f_corte,
                incluir_equivalentes_usd=bool(incluir_equivalentes_usd),
                ambito=ambito,
                moneda=moneda,
                id_centro_costo=centro_uuid,
            )
        except (ValueError, ReporteContableError) as exc:
            return {"error": str(exc)}

        logger.info(
            "contabilidad_balance_general | actor=%s | tenant=%s | cuadrada=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            reporte["ecuacion_cuadrada"],
        )
        return _serializar_salida(reporte)  # type: ignore[no-any-return]


def contabilidad_libro_mayor_auxiliar(
    capability_token: str,
    empresa_id: str,
    id_cuenta_contable: str = "",
    id_contacto: str = "",
    id_diario: str = "",
    fecha_desde: str = "",
    fecha_hasta: str = "",
    limit: int = 500,
    incluir_equivalentes_usd: bool = False,
    ambito: str = "CONSOLIDADO",
    moneda: str = "BASE",
    id_centro_costo: str = "",
) -> dict[str, Any]:
    """Consulta el Libro Mayor Auxiliar filtrado por cuenta, contacto, diario y fechas.

    Scope requerido: ``contabilidad:read``
    """
    from apps.contabilidad.services_reportes import (  # noqa: PLC0415
        ReporteContableError,
        generar_libro_mayor_auxiliar,
    )

    with _ctx(capability_token, _SCOPE, empresa_id=empresa_id) as ctx:
        try:
            empresa = _empresa_activa(ctx["empresa_id"])
            cuenta_uuid = _parse_uuid_mcp(id_cuenta_contable, "id_cuenta_contable")
            contacto_uuid = _parse_uuid_mcp(id_contacto, "id_contacto")
            diario_uuid = _parse_uuid_mcp(id_diario, "id_diario")
            centro_uuid = _parse_uuid_mcp(id_centro_costo, "id_centro_costo")
            f_desde = _parse_fecha_mcp(fecha_desde, "fecha_desde")
            f_hasta = _parse_fecha_mcp(fecha_hasta, "fecha_hasta")
            if isinstance(limit, bool):
                raise ValueError("El parámetro 'limit' debe ser entero.")
            try:
                limite_int = int(limit)
            except (ValueError, TypeError) as exc:
                raise ValueError("El parámetro 'limit' debe ser entero.") from exc
            reporte = generar_libro_mayor_auxiliar(
                empresa,
                id_cuenta_contable=cuenta_uuid,
                id_contacto=contacto_uuid,
                id_diario=diario_uuid,
                fecha_desde=f_desde,
                fecha_hasta=f_hasta,
                limit=limite_int,
                incluir_equivalentes_usd=bool(incluir_equivalentes_usd),
                ambito=ambito,
                moneda=moneda,
                id_centro_costo=centro_uuid,
            )
        except (ValueError, ReporteContableError) as exc:
            return {"error": str(exc)}

        logger.info(
            "contabilidad_libro_mayor_auxiliar | actor=%s | tenant=%s | movs=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(reporte["movimientos"]),
        )
        return _serializar_salida(reporte)  # type: ignore[no-any-return]


def contabilidad_listar_centros_costo(
    capability_token: str,
    empresa_id: str,
    tipo: str = "",
    solo_activos: bool = True,
) -> dict[str, Any]:
    """Lista los centros de costo analíticos de la empresa.

    Scope requerido: ``contabilidad:read``
    """
    from apps.contabilidad.models import CentroCosto  # noqa: PLC0415

    with _ctx(capability_token, _SCOPE, empresa_id=empresa_id) as ctx:
        try:
            empresa = _empresa_activa(ctx["empresa_id"])
            qs = CentroCosto.objects.filter(id_empresa=empresa)
            if solo_activos:
                qs = qs.filter(activo=True)
            tipo_limpio = str(tipo or "").strip().upper()
            if tipo_limpio:
                if "\x00" in tipo_limpio:
                    raise ValueError("El parámetro 'tipo' contiene caracteres inválidos.")
                qs = qs.filter(tipo=tipo_limpio)
            items = [
                {
                    "id_centro_costo": str(c.id_centro_costo),
                    "codigo": c.codigo,
                    "nombre": c.nombre,
                    "tipo": c.tipo,
                    "id_padre": str(c.id_padre_id) if c.id_padre_id else None,
                    "activo": c.activo,
                }
                for c in qs.order_by("codigo")[:200]
            ]
        except ValueError as exc:
            return {"error": str(exc)}

        logger.info(
            "contabilidad_listar_centros_costo | actor=%s | tenant=%s | total=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(items),
        )
        return {"centros_costo": items}


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": contabilidad_balance_comprobacion,
        "name": "contabilidad_balance_comprobacion",
        "scope": _SCOPE,
    },
    {
        "fn": contabilidad_estado_resultados,
        "name": "contabilidad_estado_resultados",
        "scope": _SCOPE,
    },
    {
        "fn": contabilidad_balance_general,
        "name": "contabilidad_balance_general",
        "scope": _SCOPE,
    },
    {
        "fn": contabilidad_libro_mayor_auxiliar,
        "name": "contabilidad_libro_mayor_auxiliar",
        "scope": _SCOPE,
    },
    {
        "fn": contabilidad_listar_centros_costo,
        "name": "contabilidad_listar_centros_costo",
        "scope": _SCOPE,
    },
]
