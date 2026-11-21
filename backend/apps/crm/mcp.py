"""Herramientas MCP del módulo CRM ligero (Omni Connect S4, R-CODE-7).

Herramientas expuestas:
  - ``crm_listar_pipelines`` (scope ``crm:read``)
  - ``crm_listar_leads`` (scope ``crm:read``)
  - ``crm_crear_lead`` (scope ``crm:write``)
  - ``crm_mover_etapa_lead`` (scope ``crm:write``)
  - ``crm_registrar_actividad`` (scope ``crm:write``)
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, time
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.core.exceptions import sanitize_mcp_error
from apps.crm.services import validar_sin_nul_recursivo

logger = logging.getLogger("omni.mcp.crm")

_SCOPE = "crm"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def _parse_uuid_mcp(raw: str, campo: str) -> uuid.UUID:
    texto = str(raw)
    if "\x00" in texto:
        raise ValueError(f"El parámetro '{campo}' contiene caracteres inválidos.")
    limpio = texto.strip()
    if not limpio:
        raise ValueError(f"El parámetro '{campo}' no es un UUID válido.")
    try:
        return uuid.UUID(limpio)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"El parámetro '{campo}' no es un UUID válido.") from exc


def _parse_optional_uuid_mcp(raw: str | None, campo: str) -> uuid.UUID | None:
    if raw is None:
        return None
    texto = str(raw)
    if "\x00" in texto:
        raise ValueError(f"El parámetro '{campo}' contiene caracteres inválidos.")
    if texto.strip() == "":
        return None
    return _parse_uuid_mcp(texto, campo)


def _validar_texto_mcp(valor: str | None, campo: str) -> str | None:
    if valor is None:
        return None
    texto = str(valor)
    validar_sin_nul_recursivo(texto, campo, as_value_error=True)
    return texto


def _parse_fecha_vencimiento_mcp(raw: str | None) -> datetime | None:
    if raw is None or str(raw).strip() == "":
        return None
    texto = _validar_texto_mcp(raw, "fecha_vencimiento") or ""
    dt = parse_datetime(texto.strip())
    if dt is not None:
        return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
    fecha = parse_date(texto.strip())
    if fecha is not None:
        combinado = datetime.combine(fecha, time(18, 0))
        return timezone.make_aware(combinado)
    raise ValueError("El parámetro 'fecha_vencimiento' debe estar en formato ISO (YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS).")


def _resolver_empresa(ctx: dict[str, Any]):
    from apps.core.models import Empresa  # noqa: PLC0415

    empresa_uuid = uuid.UUID(str(ctx["empresa_id"]))
    empresa = Empresa.objects.filter(pk=empresa_uuid, activo=True).first()
    if empresa is None:
        raise PermissionError("Empresa no encontrada o inactiva.")
    return empresa


def _resolver_propietario(capability_token: str, empresa, propietario_id: str | None):
    from apps.core.models import CapabilityToken, Usuarios  # noqa: PLC0415

    if propietario_id is not None and str(propietario_id).strip() != "":
        prop_uuid = _parse_uuid_mcp(str(propietario_id), "propietario_id")
        usuario = Usuarios.objects.filter(pk=prop_uuid, empresas=empresa, is_active=True).first()
        if usuario is None:
            raise PermissionError("El propietario indicado no pertenece a la empresa del token.")
        return usuario

    token_obj = (
        CapabilityToken.objects.select_related("creado_por")
        .filter(token=capability_token, empresa=empresa, activo=True)
        .first()
    )
    if (
        token_obj is not None
        and token_obj.creado_por is not None
        and token_obj.creado_por.is_active
        and token_obj.creado_por.empresas.filter(pk=empresa.pk).exists()
    ):
        return token_obj.creado_por

    usuario_empresa = Usuarios.objects.filter(empresas=empresa, is_active=True).order_by("date_joined").first()
    if usuario_empresa is not None:
        return usuario_empresa

    raise ValueError("Debe especificar propietario_id porque la empresa no tiene usuarios activos.")


def _serializar_lead_mcp(lead) -> dict[str, Any]:
    return {
        "id_lead": str(lead.id_lead),
        "id_empresa": str(lead.id_empresa_id),
        "nombre": lead.nombre,
        "apellido": lead.apellido,
        "empresa_nombre": lead.empresa_nombre,
        "email": lead.email,
        "telefono": lead.telefono,
        "fuente": lead.fuente,
        "pipeline_id": str(lead.pipeline_id),
        "pipeline_nombre": lead.pipeline.nombre,
        "etapa_id": str(lead.etapa_id),
        "etapa_nombre": lead.etapa.nombre,
        "etapa_tipo": lead.etapa.tipo,
        "propietario_id": str(lead.propietario_id),
    }


def _serializar_actividad_mcp(act) -> dict[str, Any]:
    return {
        "id_actividad": str(act.id_actividad),
        "id_empresa": str(act.id_empresa_id),
        "lead_id": str(act.lead_id),
        "tipo": act.tipo,
        "asunto": act.asunto,
        "descripcion": act.descripcion,
        "fecha_vencimiento": act.fecha_vencimiento.isoformat() if act.fecha_vencimiento else None,
        "completada": act.completada,
        "fecha_completada": act.fecha_completada.isoformat() if act.fecha_completada else None,
        "asignado_a_id": str(act.asignado_a_id) if act.asignado_a_id else None,
        "tarea_id": str(act.tarea_id) if act.tarea_id else None,
    }


def crm_listar_pipelines(
    capability_token: str,
    empresa_id: str | None = None,
    incluir_etapas: bool = True,
) -> list[dict[str, Any]]:
    """Lista los pipelines CRM activos de la empresa con sus etapas ordenadas.

    Scope requerido: ``crm:read``
    """
    from apps.crm.models import Etapa, Pipeline  # noqa: PLC0415

    emp_uuid = _parse_optional_uuid_mcp(empresa_id, "empresa_id")
    emp_str = str(emp_uuid) if emp_uuid is not None else None

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=emp_str) as ctx:
        empresa = _resolver_empresa(ctx)
        qs = Pipeline.objects.filter(id_empresa=empresa, activo=True).order_by("nombre")
        if incluir_etapas:
            qs = qs.prefetch_related(
                Prefetch("etapas", queryset=Etapa.objects.filter(activo=True).order_by("orden", "nombre"))
            )
        pipelines = list(qs)
        logger.info(
            "crm_listar_pipelines | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(pipelines),
        )
        resultado: list[dict[str, Any]] = []
        for pipe in pipelines:
            item: dict[str, Any] = {
                "id_pipeline": str(pipe.id_pipeline),
                "id_empresa": str(pipe.id_empresa_id),
                "nombre": pipe.nombre,
                "es_predeterminado": pipe.es_predeterminado,
            }
            if incluir_etapas:
                item["etapas"] = [
                    {
                        "id_etapa": str(e.id_etapa),
                        "nombre": e.nombre,
                        "orden": e.orden,
                        "tipo": e.tipo,
                    }
                    for e in pipe.etapas.all()
                ]
            resultado.append(item)
        return resultado


def crm_listar_leads(
    capability_token: str,
    empresa_id: str | None = None,
    pipeline_id: str | None = None,
    etapa_id: str | None = None,
    fuente: str | None = None,
    buscar: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Lista leads CRM activos de la empresa con filtros por pipeline, etapa, fuente y búsqueda.

    Scope requerido: ``crm:read``
    """
    from apps.crm.models import Lead  # noqa: PLC0415

    emp_uuid = _parse_optional_uuid_mcp(empresa_id, "empresa_id")
    pipe_uuid = _parse_optional_uuid_mcp(pipeline_id, "pipeline_id")
    etapa_uuid = _parse_optional_uuid_mcp(etapa_id, "etapa_id")
    fuente_val = _validar_texto_mcp(fuente, "fuente")
    buscar_val = (_validar_texto_mcp(buscar, "buscar") or "").strip()

    emp_str = str(emp_uuid) if emp_uuid is not None else None
    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=emp_str) as ctx:
        empresa = _resolver_empresa(ctx)
        qs = Lead.objects.filter(id_empresa=empresa, activo=True).select_related("pipeline", "etapa")
        if pipe_uuid is not None:
            qs = qs.filter(pipeline_id=pipe_uuid)
        if etapa_uuid is not None:
            qs = qs.filter(etapa_id=etapa_uuid)
        if fuente_val and fuente_val.strip():
            qs = qs.filter(fuente=fuente_val.strip().upper())
        if buscar_val:
            qs = qs.filter(
                Q(nombre__icontains=buscar_val)
                | Q(apellido__icontains=buscar_val)
                | Q(empresa_nombre__icontains=buscar_val)
                | Q(email__icontains=buscar_val)
                | Q(telefono__icontains=buscar_val)
            )
        tope = max(1, min(int(limit), 200))
        leads = list(qs.order_by("-fecha_creacion")[:tope])
        logger.info(
            "crm_listar_leads | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(leads),
        )
        return [_serializar_lead_mcp(lead) for lead in leads]


def crm_crear_lead(
    capability_token: str,
    empresa_id: str | None = None,
    nombre: str = "",
    apellido: str = "",
    empresa_nombre: str = "",
    email: str = "",
    telefono: str = "",
    mensaje: str = "",
    fuente: str = "MANUAL",
    pipeline_id: str | None = None,
    etapa_id: str | None = None,
    propietario_id: str | None = None,
) -> dict[str, Any]:
    """Crea un lead CRM validando aislamiento multi-tenant y ``full_clean()``.

    Scope requerido: ``crm:write``
    """
    from apps.crm.models import Etapa, Lead, Pipeline  # noqa: PLC0415
    from apps.crm.services import CrmError, crear_lead_crm  # noqa: PLC0415

    emp_uuid = _parse_optional_uuid_mcp(empresa_id, "empresa_id")
    pipe_uuid = _parse_optional_uuid_mcp(pipeline_id, "pipeline_id")
    etapa_uuid = _parse_optional_uuid_mcp(etapa_id, "etapa_id")
    prop_uuid = _parse_optional_uuid_mcp(propietario_id, "propietario_id")

    nombre_val = _validar_texto_mcp(nombre, "nombre") or ""
    apellido_val = _validar_texto_mcp(apellido, "apellido") or ""
    emp_nombre_val = _validar_texto_mcp(empresa_nombre, "empresa_nombre") or ""
    email_val = _validar_texto_mcp(email, "email") or ""
    tel_val = _validar_texto_mcp(telefono, "telefono") or ""
    msg_val = _validar_texto_mcp(mensaje, "mensaje") or ""
    fuente_val = _validar_texto_mcp(fuente, "fuente") or Lead.Fuente.MANUAL

    emp_str = str(emp_uuid) if emp_uuid is not None else None
    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=emp_str) as ctx:
        empresa = _resolver_empresa(ctx)
        propietario = _resolver_propietario(
            capability_token,
            empresa,
            str(prop_uuid) if prop_uuid is not None else None,
        )

        pipeline = None
        if pipe_uuid is not None:
            pipeline = Pipeline.objects.filter(pk=pipe_uuid, id_empresa=empresa, activo=True).first()
            if pipeline is None:
                return {"error": "Pipeline no encontrado en la empresa."}

        etapa = None
        if etapa_uuid is not None:
            etapa = (
                Etapa.objects.select_related("pipeline").filter(pk=etapa_uuid, id_empresa=empresa, activo=True).first()
            )
            if etapa is None:
                return {"error": "Etapa no encontrada en la empresa."}

        try:
            lead = crear_lead_crm(
                empresa=empresa,
                nombre=nombre_val,
                propietario=propietario,
                apellido=apellido_val,
                empresa_nombre=emp_nombre_val,
                email=email_val,
                telefono=tel_val,
                mensaje=msg_val,
                fuente=fuente_val,
                pipeline=pipeline,
                etapa=etapa,
            )
        except (CrmError, DjangoValidationError, IntegrityError, ValueError) as exc:
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="crm_crear_lead",
                    controlled_types=(CrmError, DjangoValidationError, ValueError),
                )
            }

        logger.info(
            "crm_crear_lead | actor=%s | tenant=%s | lead=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            lead.id_lead,
        )
        return _serializar_lead_mcp(lead)


def crm_mover_etapa_lead(
    capability_token: str,
    empresa_id: str | None = None,
    lead_id: str = "",
    etapa_id: str = "",
) -> dict[str, Any]:
    """Mueve un lead CRM a otra etapa dentro de su pipeline y empresa.

    Scope requerido: ``crm:write``
    """
    from apps.crm.models import Etapa, Lead  # noqa: PLC0415
    from apps.crm.services import CrmError, mover_lead_etapa  # noqa: PLC0415

    emp_uuid = _parse_optional_uuid_mcp(empresa_id, "empresa_id")
    lead_uuid = _parse_uuid_mcp(lead_id, "lead_id")
    etapa_uuid = _parse_uuid_mcp(etapa_id, "etapa_id")

    emp_str = str(emp_uuid) if emp_uuid is not None else None
    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=emp_str) as ctx:
        empresa = _resolver_empresa(ctx)
        lead = (
            Lead.objects.select_related("pipeline", "etapa")
            .filter(pk=lead_uuid, id_empresa=empresa, activo=True)
            .first()
        )
        if lead is None:
            return {"error": "Lead no encontrado en la empresa."}

        etapa = Etapa.objects.select_related("pipeline").filter(pk=etapa_uuid, id_empresa=empresa, activo=True).first()
        if etapa is None:
            return {"error": "Etapa no encontrada en la empresa."}

        try:
            lead_movido = mover_lead_etapa(lead, etapa)
        except (CrmError, DjangoValidationError, ValueError) as exc:
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="crm_mover_etapa_lead",
                    controlled_types=(CrmError, DjangoValidationError, ValueError),
                )
            }

        logger.info(
            "crm_mover_etapa_lead | actor=%s | tenant=%s | lead=%s | etapa=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            lead_movido.id_lead,
            lead_movido.etapa_id,
        )
        return _serializar_lead_mcp(lead_movido)


def crm_registrar_actividad(
    capability_token: str,
    empresa_id: str | None = None,
    lead_id: str = "",
    tipo: str = "NOTA",
    asunto: str = "",
    descripcion: str = "",
    fecha_vencimiento: str | None = None,
    completada: bool = False,
    asignado_a_id: str | None = None,
    tarea_id: str | None = None,
) -> dict[str, Any]:
    """Registra una actividad comercial sobre un lead CRM validando ``full_clean()``.

    Scope requerido: ``crm:write``
    """
    from apps.core.models import CapabilityToken, Usuarios  # noqa: PLC0415
    from apps.crm.models import Actividad, Lead  # noqa: PLC0415
    from apps.crm.services import CrmError, registrar_actividad_crm  # noqa: PLC0415
    from apps.tareas.models import Tarea  # noqa: PLC0415

    emp_uuid = _parse_optional_uuid_mcp(empresa_id, "empresa_id")
    lead_uuid = _parse_uuid_mcp(lead_id, "lead_id")
    asignado_uuid = _parse_optional_uuid_mcp(asignado_a_id, "asignado_a_id")
    tarea_uuid = _parse_optional_uuid_mcp(tarea_id, "tarea_id")

    tipo_val = _validar_texto_mcp(tipo, "tipo") or Actividad.Tipo.NOTA
    asunto_val = _validar_texto_mcp(asunto, "asunto") or ""
    desc_val = _validar_texto_mcp(descripcion, "descripcion") or ""
    venc_dt = _parse_fecha_vencimiento_mcp(fecha_vencimiento)

    emp_str = str(emp_uuid) if emp_uuid is not None else None
    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=emp_str) as ctx:
        empresa = _resolver_empresa(ctx)
        lead = Lead.objects.filter(pk=lead_uuid, id_empresa=empresa, activo=True).first()
        if lead is None:
            return {"error": "Lead no encontrado en la empresa."}

        asignado_a = None
        if asignado_uuid is not None:
            asignado_a = Usuarios.objects.filter(pk=asignado_uuid, empresas=empresa, is_active=True).first()
            if asignado_a is None:
                return {"error": "El usuario asignado no pertenece a la empresa."}

        tarea = None
        if tarea_uuid is not None:
            tarea = Tarea.objects.filter(pk=tarea_uuid, id_empresa=empresa, activo=True).first()
            if tarea is None:
                return {"error": "La tarea vinculada no pertenece a la empresa."}

        token_obj = (
            CapabilityToken.objects.select_related("creado_por")
            .filter(token=capability_token, empresa=empresa, activo=True)
            .first()
        )
        creado_por = (
            token_obj.creado_por
            if token_obj is not None
            and token_obj.creado_por is not None
            and token_obj.creado_por.empresas.filter(pk=empresa.pk).exists()
            else None
        )

        try:
            actividad = registrar_actividad_crm(
                empresa=empresa,
                lead=lead,
                tipo=tipo_val,
                asunto=asunto_val,
                descripcion=desc_val,
                fecha_vencimiento=venc_dt,
                completada=bool(completada),
                asignado_a=asignado_a,
                creado_por=creado_por,
                tarea=tarea,
            )
        except (CrmError, DjangoValidationError, IntegrityError, ValueError) as exc:
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="crm_registrar_actividad",
                    controlled_types=(CrmError, DjangoValidationError, ValueError),
                )
            }

        logger.info(
            "crm_registrar_actividad | actor=%s | tenant=%s | actividad=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            actividad.id_actividad,
        )
        return _serializar_actividad_mcp(actividad)


MCP_TOOLS: list[dict[str, Any]] = [
    {"fn": crm_listar_pipelines, "name": "crm_listar_pipelines", "scope": f"{_SCOPE}:read"},
    {"fn": crm_listar_leads, "name": "crm_listar_leads", "scope": f"{_SCOPE}:read"},
    {"fn": crm_crear_lead, "name": "crm_crear_lead", "scope": f"{_SCOPE}:write"},
    {"fn": crm_mover_etapa_lead, "name": "crm_mover_etapa_lead", "scope": f"{_SCOPE}:write"},
    {"fn": crm_registrar_actividad, "name": "crm_registrar_actividad", "scope": f"{_SCOPE}:write"},
]
