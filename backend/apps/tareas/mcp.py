"""Herramientas MCP de ``apps/tareas`` — Ejecución operativa y minutas IA-Native (R-CODE-7 / ADR-015)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.utils.dateparse import parse_date

logger = logging.getLogger("omni.mcp.tareas")

_SCOPE = "tareas"


def _ctx(capability_token: str, scope: str) -> dict[str, Any]:
    from apps.core.mcp_server import _require_scope, _resolve_token  # noqa: PLC0415

    context = _resolve_token(capability_token)
    _require_scope(context, scope)
    assert context is not None  # nosec B101
    return context


def _empresa_activa(empresa_id: str, ctx: dict[str, Any]):
    from apps.core.models import Empresa  # noqa: PLC0415

    try:
        uuid.UUID(str(empresa_id))
    except (ValueError, TypeError) as exc:
        raise PermissionError("empresa_id inválido.") from exc

    if str(empresa_id) != ctx["empresa_id"]:
        raise PermissionError("empresa_id no coincide con el tenant del token.")

    empresa = Empresa.objects.filter(id_empresa=ctx["empresa_id"], activo=True).first()
    if empresa is None:
        raise PermissionError("Empresa inactiva o no encontrada.")
    return empresa


def tareas_listar(
    capability_token: str,
    empresa_id: str,
    estado: str | None = None,
    asignado_a_id: str | None = None,
    entidad_tipo: str | None = None,
    entidad_id: str | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Lista tareas operativas activas de la empresa con filtros opcionales.

    Scope requerido: ``tareas:read``
    """
    from apps.tareas.models import Tarea  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    empresa = _empresa_activa(empresa_id, ctx)

    qs = Tarea.objects.filter(id_empresa=empresa, activo=True).select_related(
        "proyecto", "seccion", "area", "asignado_a"
    )
    if estado:
        qs = qs.filter(estado=estado)
    if asignado_a_id:
        uuid.UUID(str(asignado_a_id))
        qs = qs.filter(asignado_a_id=asignado_a_id)
    if entidad_tipo:
        qs = qs.filter(entidad_tipo=entidad_tipo)
    if entidad_id:
        uuid.UUID(str(entidad_id))
        qs = qs.filter(entidad_id=entidad_id)

    tope = max(1, min(int(limite), 200))
    filas = list(qs[:tope])
    logger.info(
        "tareas_listar | actor=%s | tenant=%s | devueltas=%d",
        ctx["actor_id"],
        ctx["tenant_id"],
        len(filas),
    )
    return [
        {
            "id_tarea": str(t.id_tarea),
            "titulo": t.titulo,
            "estado": t.estado,
            "prioridad": t.prioridad,
            "proyecto": t.proyecto.nombre if t.proyecto else None,
            "seccion": t.seccion.nombre if t.seccion else None,
            "area": t.area.nombre if t.area else None,
            "asignado_a": (
                t.asignado_a.get_full_name().strip() or t.asignado_a.username
                if t.asignado_a
                else None
            ),
            "fecha_vencimiento": (
                t.fecha_vencimiento.isoformat() if t.fecha_vencimiento else None
            ),
            "bloqueada_por_escalacion": t.bloqueada_por_escalacion,
            "entidad_tipo": t.entidad_tipo or None,
            "entidad_id": str(t.entidad_id) if t.entidad_id else None,
        }
        for t in filas
    ]


def tareas_resumen_equipo(
    capability_token: str,
    empresa_id: str,
    fecha: str | None = None,
) -> dict[str, Any]:
    """Devuelve el resumen ejecutivo de tareas abiertas, vencidas y bloqueadas por área y persona.

    Scope requerido: ``tareas:read``
    """
    from apps.tareas.services import resumen_ejecutivo_equipo  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:read")
    empresa = _empresa_activa(empresa_id, ctx)
    fecha_corte = parse_date(fecha) if fecha else None
    logger.info(
        "tareas_resumen_equipo | actor=%s | tenant=%s", ctx["actor_id"], ctx["tenant_id"]
    )
    return resumen_ejecutivo_equipo(empresa, hoy=fecha_corte)


def tareas_crear(
    capability_token: str,
    empresa_id: str,
    titulo: str,
    descripcion: str = "",
    prioridad: str = "MEDIA",
    asignado_a_id: str | None = None,
    area_id: str | None = None,
    proyecto_id: str | None = None,
    fecha_vencimiento: str | None = None,
    entidad_tipo: str = "",
    entidad_id: str | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Crea una tarea operativa de forma idempotente y la ubica en el tablero correspondiente.

    Scope requerido: ``tareas:write``
    """
    from apps.core.models import Usuarios  # noqa: PLC0415
    from apps.tareas.models import AreaOperativa, Proyecto, Tarea  # noqa: PLC0415
    from apps.tareas.services import TareaError, crear_tarea  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:write")
    empresa = _empresa_activa(empresa_id, ctx)

    asignado = None
    if asignado_a_id:
        asignado = Usuarios.objects.filter(
            pk=uuid.UUID(str(asignado_a_id)), empresas=empresa, is_active=True
        ).first()
        if asignado is None:
            return {"error": "Usuario asignado no pertenece a la empresa."}

    area = None
    if area_id:
        area = AreaOperativa.objects.filter(
            pk=uuid.UUID(str(area_id)), id_empresa=empresa, activo=True
        ).first()
        if area is None:
            return {"error": "Área no encontrada en la empresa."}

    proyecto = None
    if proyecto_id:
        proyecto = Proyecto.objects.filter(
            pk=uuid.UUID(str(proyecto_id)), id_empresa=empresa, activo=True
        ).first()
        if proyecto is None:
            return {"error": "Proyecto no encontrado en la empresa."}

    entidad_uuid = uuid.UUID(str(entidad_id)) if entidad_id else None
    venc = parse_date(fecha_vencimiento) if fecha_vencimiento else None

    try:
        tarea, creada = crear_tarea(
            empresa=empresa,
            titulo=titulo,
            descripcion=descripcion,
            prioridad=prioridad,
            origen=Tarea.Origen.AGENTE,
            proyecto=proyecto,
            area=area,
            asignado_a=asignado,
            fecha_vencimiento=venc,
            entidad_tipo=entidad_tipo,
            entidad_id=entidad_uuid,
            idempotency_key=idempotency_key,
        )
    except TareaError as exc:
        return {"error": exc.args[0]}

    logger.info(
        "tareas_crear | actor=%s | tenant=%s | tarea=%s | creada=%s",
        ctx["actor_id"],
        ctx["tenant_id"],
        tarea.id_tarea,
        creada,
    )
    return {
        "id_tarea": str(tarea.id_tarea),
        "titulo": tarea.titulo,
        "estado": tarea.estado,
        "creada": creada,
    }


def tareas_cambiar_estado(
    capability_token: str,
    empresa_id: str,
    tarea_id: str,
    nuevo_estado: str,
    motivo: str = "",
) -> dict[str, Any]:
    """Cambia el estado de una tarea y sincroniza su columna Kanban.

    Scope requerido: ``tareas:write``
    """
    from apps.tareas.models import Tarea  # noqa: PLC0415
    from apps.tareas.services import TareaError, cambiar_estado_tarea  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:write")
    empresa = _empresa_activa(empresa_id, ctx)

    tarea = Tarea.objects.filter(
        pk=uuid.UUID(str(tarea_id)), id_empresa=empresa, activo=True
    ).first()
    if tarea is None:
        return {"error": "Tarea no encontrada en la empresa."}

    try:
        actualizada = cambiar_estado_tarea(
            tarea=tarea, nuevo_estado=nuevo_estado, motivo=motivo
        )
    except TareaError as exc:
        return {"error": exc.args[0]}

    logger.info(
        "tareas_cambiar_estado | actor=%s | tenant=%s | tarea=%s | estado=%s",
        ctx["actor_id"],
        ctx["tenant_id"],
        tarea.id_tarea,
        actualizada.estado,
    )
    return {
        "id_tarea": str(actualizada.id_tarea),
        "estado": actualizada.estado,
        "completada_en": (
            actualizada.completada_en.isoformat() if actualizada.completada_en else None
        ),
    }


def tareas_crear_minuta_borrador(
    capability_token: str,
    empresa_id: str,
    titulo: str,
    items_propuestos: list[dict[str, Any]],
    texto_fuente: str = "",
    fecha_reunion: str | None = None,
) -> dict[str, Any]:
    """Registra una minuta enriqueciendo responsables/áreas y fechas relativas como borrador.

    Scope requerido: ``tareas:write``
    """
    from apps.tareas.services import TareaError, crear_minuta_borrador  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:write")
    empresa = _empresa_activa(empresa_id, ctx)
    fecha = parse_date(fecha_reunion) if fecha_reunion else None

    try:
        minuta = crear_minuta_borrador(
            empresa=empresa,
            titulo=titulo,
            fecha_reunion=fecha,
            texto_fuente=texto_fuente,
            items_propuestos=items_propuestos,
        )
    except TareaError as exc:
        return {"error": exc.args[0]}

    logger.info(
        "tareas_crear_minuta_borrador | actor=%s | tenant=%s | minuta=%s | items=%d",
        ctx["actor_id"],
        ctx["tenant_id"],
        minuta.id_minuta,
        len(minuta.borrador_tareas),
    )
    return {
        "id_minuta": str(minuta.id_minuta),
        "estado": minuta.estado,
        "borrador_tareas": minuta.borrador_tareas,
    }


def tareas_confirmar_minuta(
    capability_token: str,
    empresa_id: str,
    minuta_id: str,
    items_confirmados: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Confirma el borrador de una minuta y crea las tareas correspondientes en una transacción.

    Scope requerido: ``tareas:write``
    """
    from apps.tareas.models import MinutaReunion  # noqa: PLC0415
    from apps.tareas.services import TareaError, confirmar_minuta  # noqa: PLC0415

    ctx = _ctx(capability_token, f"{_SCOPE}:write")
    empresa = _empresa_activa(empresa_id, ctx)
    minuta = MinutaReunion.objects.filter(
        pk=uuid.UUID(str(minuta_id)), id_empresa=empresa, activo=True
    ).first()
    if minuta is None:
        return {"error": "Minuta no encontrada en la empresa."}

    try:
        creadas = confirmar_minuta(minuta=minuta, items_confirmados=items_confirmados)
    except TareaError as exc:
        return {"error": exc.args[0]}

    logger.info(
        "tareas_confirmar_minuta | actor=%s | tenant=%s | minuta=%s | tareas=%d",
        ctx["actor_id"],
        ctx["tenant_id"],
        minuta.id_minuta,
        len(creadas),
    )
    return {
        "id_minuta": str(minuta.id_minuta),
        "estado": minuta.estado,
        "tareas_creadas": [str(t.id_tarea) for t in creadas],
    }


MCP_TOOLS: list[dict[str, Any]] = [
    {"fn": tareas_listar, "name": "tareas_listar", "scope": f"{_SCOPE}:read"},
    {
        "fn": tareas_resumen_equipo,
        "name": "tareas_resumen_equipo",
        "scope": f"{_SCOPE}:read",
    },
    {"fn": tareas_crear, "name": "tareas_crear", "scope": f"{_SCOPE}:write"},
    {
        "fn": tareas_cambiar_estado,
        "name": "tareas_cambiar_estado",
        "scope": f"{_SCOPE}:write",
    },
    {
        "fn": tareas_crear_minuta_borrador,
        "name": "tareas_crear_minuta_borrador",
        "scope": f"{_SCOPE}:write",
    },
    {
        "fn": tareas_confirmar_minuta,
        "name": "tareas_confirmar_minuta",
        "scope": f"{_SCOPE}:write",
    },
]
