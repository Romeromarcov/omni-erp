"""Servicios transaccionales del CRM ligero (Omni Connect S4)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.connect.models import Perfil, Tarjeta
from apps.core.exceptions import DomainError
from apps.core.models import Contacto, Empresa, Usuarios
from apps.core.validators import normalizar_email, normalizar_telefono
from apps.tareas.models import Tarea

from .models import Actividad, Etapa, Lead, Pipeline
from .services_dedup import resolver_o_vincular_contacto


class CrmError(DomainError):
    """Error de dominio controlado del módulo CRM / Kanban."""


def validar_sin_nul_recursivo(
    valor: Any,
    campo: str = "error",
    *,
    as_value_error: bool = False,
) -> None:
    """Rechaza bytes NUL (``\\x00``) en strings, listas o mapeos anidados."""
    if isinstance(valor, Mapping):
        for key, item in valor.items():
            if "\x00" in str(key):
                _raise_nul_error(campo, as_value_error=as_value_error)
            validar_sin_nul_recursivo(item, str(key), as_value_error=as_value_error)
    elif isinstance(valor, (list, tuple)):
        for item in valor:
            validar_sin_nul_recursivo(item, campo, as_value_error=as_value_error)
    elif isinstance(valor, str) and "\x00" in valor:
        _raise_nul_error(campo, as_value_error=as_value_error)


def _raise_nul_error(campo: str, *, as_value_error: bool) -> None:
    if as_value_error:
        raise ValueError(f"El parámetro '{campo}' contiene caracteres inválidos.")
    raise DjangoValidationError({campo: "El valor contiene caracteres inválidos."})


def asegurar_pipeline_empresa(empresa: Empresa) -> Pipeline:
    """Obtiene o inicializa idempotentemente el pipeline predeterminado con sus etapas base."""
    from apps.connect.services import asegurar_pipeline_predeterminado  # noqa: PLC0415

    return asegurar_pipeline_predeterminado(empresa)


@transaction.atomic
def mover_lead_etapa(
    lead: Lead,
    nueva_etapa: Etapa,
    usuario: Usuarios | None = None,
) -> Lead:
    """Mueve un ``Lead`` a otra ``Etapa`` del mismo pipeline y empresa validando ``full_clean()``."""
    lead_locked = Lead.objects.select_for_update().select_related("pipeline", "etapa").get(pk=lead.pk)
    if not lead_locked.activo:
        raise CrmError("No se puede mover un lead inactivo.")

    etapa_obj = Etapa.objects.select_related("pipeline").filter(pk=nueva_etapa.pk).first()
    if etapa_obj is None or not etapa_obj.activo:
        raise CrmError("La etapa destino no existe o está inactiva.")

    if etapa_obj.id_empresa_id != lead_locked.id_empresa_id:
        raise CrmError("La etapa destino pertenece a otra empresa.")

    if etapa_obj.pipeline_id != lead_locked.pipeline_id:
        raise CrmError("La etapa destino no pertenece al pipeline del lead.")

    if usuario is not None:
        from apps.core.viewsets import get_empresas_visible  # noqa: PLC0415

        es_super = bool(getattr(usuario, "es_superusuario_omni", False) or getattr(usuario, "is_superuser", False))
        if not es_super and not get_empresas_visible(usuario).filter(pk=lead_locked.id_empresa_id).exists():
            raise CrmError("El usuario no tiene acceso a la empresa del lead.")

    lead_locked.etapa = etapa_obj
    lead_locked.full_clean()
    lead_locked.save(update_fields=["etapa", "fecha_actualizacion"])
    return lead_locked


@transaction.atomic
def reordenar_etapas_pipeline(pipeline: Pipeline, etapa_ids: list[uuid.UUID]) -> list[Etapa]:
    """Reordena atómicamente todas las etapas activas de un ``Pipeline``."""
    pipe_locked = Pipeline.objects.select_for_update().get(pk=pipeline.pk)
    if not pipe_locked.activo:
        raise CrmError("No se pueden reordenar etapas de un pipeline inactivo.")

    etapas = list(
        Etapa.objects.select_for_update()
        .filter(pipeline=pipe_locked, id_empresa_id=pipe_locked.id_empresa_id, activo=True)
        .order_by("orden", "fecha_creacion")
    )
    etapas_map = {etapa.id_etapa: etapa for etapa in etapas}

    if len(set(etapa_ids)) != len(etapa_ids):
        raise CrmError("No se permiten etapas duplicadas al reordenar.")
    if any(eid not in etapas_map for eid in etapa_ids):
        raise CrmError("Una o más etapas no pertenecen al pipeline activo.")
    if set(etapa_ids) != set(etapas_map):
        raise CrmError("Debe incluir todas las etapas activas del pipeline para reordenar.")

    ordenadas: list[Etapa] = []
    for idx, eid in enumerate(etapa_ids, start=1):
        etapa = etapas_map[eid]
        etapa.orden = idx
        etapa.full_clean()
        etapa.save(update_fields=["orden", "fecha_actualizacion"])
        ordenadas.append(etapa)
    return ordenadas


@transaction.atomic
def crear_lead_crm(
    *,
    empresa: Empresa,
    nombre: str,
    propietario: Usuarios,
    apellido: str = "",
    empresa_nombre: str = "",
    email: str = "",
    telefono: str = "",
    mensaje: str = "",
    fuente: str = Lead.Fuente.MANUAL,
    pipeline: Pipeline | None = None,
    etapa: Etapa | None = None,
    tarjeta: Tarjeta | None = None,
    perfil: Perfil | None = None,
    contacto: Contacto | None = None,
    consentimiento_aceptado: bool = False,
    consentimiento_fecha: datetime | None = None,
    consentimiento_texto: str = "",
) -> Lead:
    """Crea un ``Lead`` validando tenant, pipeline/etapa, normalización y ``full_clean()``."""
    nombre_limpio = (nombre or "").strip()
    if not nombre_limpio:
        raise CrmError("El nombre del lead es obligatorio.")

    pipeline_obj = pipeline
    if pipeline_obj is None and etapa is not None:
        pipeline_obj = etapa.pipeline
    if pipeline_obj is None:
        pipeline_obj = asegurar_pipeline_empresa(empresa)

    if pipeline_obj.id_empresa_id != empresa.pk or not pipeline_obj.activo:
        raise CrmError("El pipeline seleccionado no pertenece a la empresa o está inactivo.")

    etapa_obj = etapa
    if etapa_obj is None:
        etapa_obj = (
            Etapa.objects.filter(
                id_empresa=empresa,
                pipeline=pipeline_obj,
                activo=True,
                tipo=Etapa.Tipo.ABIERTA,
            )
            .order_by("orden", "fecha_creacion")
            .first()
            or Etapa.objects.filter(
                id_empresa=empresa,
                pipeline=pipeline_obj,
                activo=True,
            )
            .order_by("orden", "fecha_creacion")
            .first()
        )
        if etapa_obj is None:
            raise CrmError("El pipeline seleccionado no tiene etapas activas.")
    else:
        if etapa_obj.id_empresa_id != empresa.pk or not etapa_obj.activo:
            raise CrmError("La etapa seleccionada no pertenece a la empresa o está inactiva.")
        if etapa_obj.pipeline_id != pipeline_obj.pk:
            raise CrmError("La etapa seleccionada no pertenece al pipeline indicado.")

    fuente_norm = (fuente or Lead.Fuente.MANUAL).strip().upper()
    if fuente_norm not in (Lead.Fuente.MANUAL, Lead.Fuente.IMPORTACION) and not consentimiento_aceptado:
        raise CrmError("Los leads de canales públicos requieren consentimiento aceptado.")

    consent_texto_limpio = (consentimiento_texto or "").strip()
    consent_fecha_final = consentimiento_fecha
    if consentimiento_aceptado:
        if not consent_texto_limpio:
            raise CrmError("Debe indicar el texto de consentimiento cuando el consentimiento fue aceptado.")
        consent_fecha_final = consent_fecha_final or timezone.now()
    else:
        consent_fecha_final = None
        consent_texto_limpio = ""

    email_limpio = (email or "").strip()
    telefono_limpio = (telefono or "").strip()
    apellido_limpio = (apellido or "").strip()
    empresa_nombre_limpio = (empresa_nombre or "").strip()

    contacto_resuelto = contacto
    if contacto_resuelto is None:
        contacto_resuelto = resolver_o_vincular_contacto(
            empresa,
            nombre=nombre_limpio,
            apellido=apellido_limpio,
            email=email_limpio,
            telefono=telefono_limpio,
            empresa_nombre=empresa_nombre_limpio,
        )

    lead = Lead(
        id_empresa=empresa,
        nombre=nombre_limpio,
        apellido=apellido_limpio,
        empresa_nombre=empresa_nombre_limpio,
        email=email_limpio,
        telefono=telefono_limpio,
        email_normalizado=normalizar_email(email_limpio),
        telefono_normalizado=normalizar_telefono(telefono_limpio),
        mensaje=(mensaje or "").strip(),
        fuente=fuente_norm,
        tarjeta=tarjeta,
        perfil=perfil,
        pipeline=pipeline_obj,
        etapa=etapa_obj,
        propietario=propietario,
        contacto=contacto_resuelto,
        consentimiento_aceptado=bool(consentimiento_aceptado),
        consentimiento_fecha=consent_fecha_final,
        consentimiento_texto=consent_texto_limpio,
    )
    lead.full_clean()
    lead.save()
    return lead


@transaction.atomic
def registrar_actividad_crm(
    *,
    empresa: Empresa,
    lead: Lead,
    tipo: str,
    asunto: str,
    descripcion: str = "",
    fecha_vencimiento: datetime | None = None,
    completada: bool = False,
    asignado_a: Usuarios | None = None,
    creado_por: Usuarios | None = None,
    tarea: Tarea | None = None,
) -> Actividad:
    """Registra una ``Actividad`` sobre un ``Lead`` validando aislamiento multi-tenant."""
    if not lead.activo or lead.id_empresa_id != empresa.pk:
        raise CrmError("El lead no existe en la empresa o está inactivo.")

    asunto_limpio = (asunto or "").strip()
    if not asunto_limpio:
        raise CrmError("El asunto de la actividad es obligatorio.")

    actividad = Actividad(
        id_empresa=empresa,
        lead=lead,
        tipo=(tipo or Actividad.Tipo.NOTA).strip().upper(),
        asunto=asunto_limpio,
        descripcion=(descripcion or "").strip(),
        fecha_vencimiento=fecha_vencimiento,
        completada=bool(completada),
        fecha_completada=timezone.now() if completada else None,
        asignado_a=asignado_a,
        creado_por=creado_por,
        tarea=tarea,
    )
    actividad.full_clean()
    actividad.save()
    return actividad


@transaction.atomic
def completar_actividad(
    actividad: Actividad,
    completada: bool = True,
    *,
    descripcion: str | None = None,
) -> Actividad:
    """Marca o desmarca una ``Actividad`` como completada de forma transaccional."""
    act_locked = Actividad.objects.select_for_update().get(pk=actividad.pk)
    if not act_locked.activo:
        raise CrmError("No se puede actualizar una actividad inactiva.")

    act_locked.completada = bool(completada)
    act_locked.fecha_completada = timezone.now() if act_locked.completada else None
    if descripcion is not None:
        act_locked.descripcion = descripcion.strip()
    act_locked.full_clean()
    act_locked.save()
    return act_locked
