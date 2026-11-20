"""Herramientas MCP de Gestión de Aprobaciones (ADR-003).

Herramientas expuestas:
  - ``aprobaciones_pendientes`` (scope ``aprobaciones:read``)
  - ``aprobaciones_decidir``    (scope ``aprobaciones:write``)
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("omni.mcp.gestion_aprobaciones")


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def _parse_uuid_mcp(raw: str, campo: str) -> uuid.UUID:
    limpio = str(raw or "").strip()
    if not limpio or "\x00" in limpio:
        raise ValueError(f"El parámetro '{campo}' es inválido.")
    try:
        return uuid.UUID(limpio)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"El parámetro '{campo}' no es un UUID válido.") from exc


def aprobaciones_pendientes(
    capability_token: str,
    empresa_id: str,
    codigo_tipo: str = "",
    solo_escaladas: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Lista las solicitudes de aprobación pendientes de una empresa.

    Scope requerido: ``aprobaciones:read``
    """
    from apps.gestion_aprobaciones.models import SolicitudAprobacion  # noqa: PLC0415
    from apps.gestion_aprobaciones.services import PENDIENTE  # noqa: PLC0415

    with _ctx(capability_token, "aprobaciones:read", empresa_id=empresa_id) as ctx:
        try:
            emp_uuid = _parse_uuid_mcp(empresa_id, "empresa_id")
            if isinstance(limit, bool):
                raise ValueError("El parámetro 'limit' debe ser entero.")
            limite_int = min(max(int(limit), 1), 200)
        except (ValueError, TypeError) as exc:
            return {"error": str(exc)}

        qs = (
            SolicitudAprobacion.objects.filter(
                id_tipo_aprobacion__id_empresa_id=emp_uuid,
                estado_solicitud=PENDIENTE,
            )
            .select_related("id_tipo_aprobacion", "etapa_actual_flujo", "id_departamento", "id_usuario_solicitante")
            .order_by("fecha_inicio_etapa", "pk")
        )
        if codigo_tipo and codigo_tipo.strip():
            qs = qs.filter(id_tipo_aprobacion__codigo_tipo=codigo_tipo.strip())
        if solo_escaladas:
            qs = qs.filter(escalada=True)

        items = list(qs[:limite_int])
        logger.info(
            "aprobaciones_pendientes | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(items),
        )
        return [
            {
                "id_solicitud_aprobacion": str(s.pk),
                "codigo_tipo": s.id_tipo_aprobacion.codigo_tipo,
                "nombre_tipo": s.id_tipo_aprobacion.nombre_tipo,
                "nombre_modelo_origen": s.nombre_modelo_origen,
                "id_entidad_origen": str(s.id_entidad_origen),
                "monto": str(s.monto) if s.monto is not None else None,
                "estado_solicitud": s.estado_solicitud,
                "etapa_actual": s.etapa_actual_flujo.nombre_etapa if s.etapa_actual_flujo else None,
                "id_departamento": str(s.id_departamento_id) if s.id_departamento_id else None,
                "escalada": s.escalada,
                "fecha_solicitud": s.fecha_solicitud.isoformat() if s.fecha_solicitud else None,
                "fecha_inicio_etapa": s.fecha_inicio_etapa.isoformat() if s.fecha_inicio_etapa else None,
                "fecha_escalacion": s.fecha_escalacion.isoformat() if s.fecha_escalacion else None,
            }
            for s in items
        ]


def aprobaciones_decidir(
    capability_token: str,
    empresa_id: str,
    solicitud_id: str,
    usuario_id: str,
    aprobado: bool,
    comentarios: str = "",
) -> dict[str, Any]:
    """Registra la decisión (aprobar/rechazar) de un aprobador autorizado sobre una solicitud.

    Scope requerido: ``aprobaciones:write``
    """
    from apps.core.models import Usuarios  # noqa: PLC0415
    from apps.gestion_aprobaciones.models import SolicitudAprobacion  # noqa: PLC0415
    from apps.gestion_aprobaciones.services import AprobacionError, registrar_decision  # noqa: PLC0415

    with _ctx(capability_token, "aprobaciones:write", empresa_id=empresa_id) as ctx:
        try:
            emp_uuid = _parse_uuid_mcp(empresa_id, "empresa_id")
            sol_uuid = _parse_uuid_mcp(solicitud_id, "solicitud_id")
            usr_uuid = _parse_uuid_mcp(usuario_id, "usuario_id")
            if not isinstance(aprobado, bool):
                raise ValueError("El parámetro 'aprobado' debe ser booleano (true/false).")
            solicitud = SolicitudAprobacion.objects.filter(
                pk=sol_uuid,
                id_tipo_aprobacion__id_empresa_id=emp_uuid,
            ).first()
            if solicitud is None:
                raise ValueError("Solicitud de aprobación no encontrada en la empresa.")
            usuario = Usuarios.objects.filter(pk=usr_uuid, empresas__id_empresa=emp_uuid, is_active=True).first()
            if usuario is None:
                raise ValueError("Usuario aprobador no encontrado o inactivo en la empresa.")
            actualizada = registrar_decision(solicitud, usuario, aprobado, comentarios=str(comentarios or ""))
        except (ValueError, AprobacionError) as exc:
            return {"error": str(exc)}

        logger.info(
            "aprobaciones_decidir | actor=%s | tenant=%s | solicitud=%s | estado=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            actualizada.pk,
            actualizada.estado_solicitud,
        )
        return {
            "id_solicitud_aprobacion": str(actualizada.pk),
            "estado_solicitud": actualizada.estado_solicitud,
            "etapa_actual": actualizada.etapa_actual_flujo.nombre_etapa if actualizada.etapa_actual_flujo else None,
            "escalada": actualizada.escalada,
            "monto": str(actualizada.monto) if actualizada.monto is not None else None,
        }


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": aprobaciones_pendientes,
        "name": "aprobaciones_pendientes",
        "scope": "aprobaciones:read",
    },
    {
        "fn": aprobaciones_decidir,
        "name": "aprobaciones_decidir",
        "scope": "aprobaciones:write",
    },
]
