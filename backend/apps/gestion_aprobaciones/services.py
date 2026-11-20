"""
Lógica de negocio de aprobaciones configurables por tenant, monto, departamento y SLA.

Una ``TipoAprobacion`` (por empresa, ``codigo_tipo`` p. ej. ORDEN_COMPRA / GASTO)
agrupa etapas ``FlujoAprobacion`` con rangos de monto (``monto_minimo`` /
``monto_maximo``), departamento opcional (``id_departamento``), SLA en horas
(``sla_horas``) y aprobador/escalación (rol o usuario).

Funciones públicas:
  evaluar_etapas()              — etapas aplicables a un (empresa, tipo, monto, departamento)
  requiere_aprobacion()         — ¿hay alguna etapa aplicable?
  crear_solicitud()             — crea (o devuelve) la solicitud PENDIENTE del documento
  registrar_decision()          — registra una decisión y avanza/cierra la solicitud
  esta_aprobada()               — ¿el documento tiene una solicitud APROBADA?
  escalar_solicitudes_vencidas()— escala solicitudes PENDIENTE cuyo SLA venció
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import logging
import uuid

from django.db import transaction
from django.utils import timezone

from apps.core import rls

logger = logging.getLogger(__name__)

PENDIENTE = "PENDIENTE"
APROBADA = "APROBADA"
RECHAZADA = "RECHAZADA"


class AprobacionError(Exception):
    pass


def _nombre_modelo_documento(documento) -> str:
    return getattr(documento, "nombre_modelo_aprobacion", None) or documento.__class__.__name__


def _resolver_entidad_uuid(documento) -> uuid.UUID:
    pk = getattr(documento, "pk", None)
    if isinstance(pk, uuid.UUID):
        return pk
    try:
        return uuid.UUID(str(pk))
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"omni:{_nombre_modelo_documento(documento)}:{pk}")


def _usuario_en_empresa(usuario, empresa_id) -> bool:
    if getattr(usuario, "es_superusuario_omni", False):
        return True
    empresas_rel = getattr(usuario, "empresas", None)
    if empresas_rel is None:
        return False
    return empresas_rel.filter(pk=empresa_id).exists()


def _verificar_aprobador(etapa, usuario, *, solicitud=None) -> None:
    """Verifica que ``usuario`` sea el aprobador designado de la etapa (SoD/authz).

    - Valida pertenencia del usuario a la empresa del flujo.
    - Si ``solicitud`` fue escalada, autoriza también a ``escalar_a_usuario`` o
      a usuarios con ``escalar_a_rol``.
    - Si la etapa fija ``id_usuario_aprobador``: debe ser ese usuario exacto.
    - Si fija ``rol_aprobador``: el usuario debe tener ese rol (``UsuarioRoles``).
    - Si no fija ninguno: etapa abierta — cualquier usuario del tenant puede
      decidir.
    """
    empresa_id = etapa.id_tipo_aprobacion.id_empresa_id
    if not _usuario_en_empresa(usuario, empresa_id):
        raise AprobacionError("El usuario no pertenece a la empresa de la solicitud.")

    if solicitud is not None and getattr(solicitud, "escalada", False):
        if etapa.escalar_a_usuario_id is not None and etapa.escalar_a_usuario_id == usuario.pk:
            return
        if etapa.escalar_a_rol_id is not None:
            from apps.core.models import UsuarioRoles

            if UsuarioRoles.objects.filter(id_usuario=usuario, id_rol=etapa.escalar_a_rol_id).exists():
                return

    if etapa.id_usuario_aprobador_id is not None:
        if etapa.id_usuario_aprobador_id != usuario.pk:
            raise AprobacionError("No es el aprobador designado para esta etapa.")
        return
    if etapa.rol_aprobador_id is not None:
        from apps.core.models import UsuarioRoles

        if not UsuarioRoles.objects.filter(id_usuario=usuario, id_rol=etapa.rol_aprobador_id).exists():
            raise AprobacionError("No posee el rol aprobador requerido para esta etapa.")


def _etapa_aplica(etapa, monto: Decimal | None) -> bool:
    """True si ``monto`` cae dentro del rango [monto_minimo, monto_maximo] de la
    etapa. Los límites nulos se interpretan como abiertos (sin tope)."""
    if monto is None:
        return etapa.monto_minimo is None and etapa.monto_maximo is None
    if etapa.monto_minimo is not None and monto < etapa.monto_minimo:
        return False
    if etapa.monto_maximo is not None and monto > etapa.monto_maximo:
        return False
    return True


def evaluar_etapas(empresa, codigo_tipo: str, monto, departamento=None) -> list:
    """Devuelve las etapas de flujo aplicables (activas, con el monto en rango),
    ordenadas por ``orden_etapa``. Si ``departamento`` tiene etapas activas
    configuradas en ese ``TipoAprobacion``, prioriza exclusivamente el flujo
    departamental; de lo contrario cae al flujo general (``id_departamento=None``).
    """
    from .models import FlujoAprobacion, TipoAprobacion

    monto_dec = Decimal(str(monto))
    tipo = TipoAprobacion.objects.filter(id_empresa=empresa, codigo_tipo=codigo_tipo, activo=True).first()
    if tipo is None:
        return []

    base_qs = FlujoAprobacion.objects.filter(id_tipo_aprobacion=tipo, activo=True).order_by("orden_etapa")
    if departamento is not None:
        if hasattr(departamento, "id_empresa_id") and str(departamento.id_empresa_id) != str(empresa.pk):
            raise AprobacionError("El departamento no pertenece a la empresa de la regla de aprobación.")
        dep_id = getattr(departamento, "pk", departamento)
        etapas_dep = list(base_qs.filter(id_departamento_id=dep_id))
        if etapas_dep:
            return [e for e in etapas_dep if _etapa_aplica(e, monto_dec)]

    etapas_gen = list(base_qs.filter(id_departamento__isnull=True))
    return [e for e in etapas_gen if _etapa_aplica(e, monto_dec)]


def requiere_aprobacion(empresa, codigo_tipo: str, monto, departamento=None) -> bool:
    return bool(evaluar_etapas(empresa, codigo_tipo, monto, departamento=departamento))


def esta_aprobada(documento, *, monto_minimo_aprobado: Decimal | None = None) -> bool:
    """True si el documento tiene una SolicitudAprobacion en estado APROBADA."""
    from .models import SolicitudAprobacion

    qs = SolicitudAprobacion.objects.filter(
        id_entidad_origen=_resolver_entidad_uuid(documento),
        nombre_modelo_origen=_nombre_modelo_documento(documento),
        estado_solicitud=APROBADA,
    )
    if monto_minimo_aprobado is not None:
        qs = qs.filter(monto__gte=monto_minimo_aprobado)
    return qs.exists()


def _solicitud_abierta(documento):
    from .models import SolicitudAprobacion

    return SolicitudAprobacion.objects.filter(
        id_entidad_origen=_resolver_entidad_uuid(documento),
        nombre_modelo_origen=_nombre_modelo_documento(documento),
        estado_solicitud=PENDIENTE,
    ).first()


@transaction.atomic
def crear_solicitud(documento, empresa, usuario, codigo_tipo: str, monto, *, departamento=None):
    """Crea la SolicitudAprobacion PENDIENTE del documento (idempotente: si ya hay
    una abierta, la devuelve). Devuelve None si el monto no requiere aprobación."""
    from .models import SolicitudAprobacion

    etapas = evaluar_etapas(empresa, codigo_tipo, monto, departamento=departamento)
    if not etapas:
        return None

    abierta = _solicitud_abierta(documento)
    if abierta is not None:
        return abierta

    dep_obj = departamento if hasattr(departamento, "pk") else None
    return SolicitudAprobacion.objects.create(
        id_tipo_aprobacion=etapas[0].id_tipo_aprobacion,
        id_departamento=dep_obj,
        id_entidad_origen=_resolver_entidad_uuid(documento),
        nombre_modelo_origen=_nombre_modelo_documento(documento),
        id_usuario_solicitante=usuario,
        estado_solicitud=PENDIENTE,
        etapa_actual_flujo=etapas[0],
        monto=Decimal(str(monto)),
        fecha_inicio_etapa=timezone.now(),
        escalada=False,
        fecha_escalacion=None,
    )


@transaction.atomic
def registrar_decision(solicitud, usuario, aprobado: bool, comentarios: str = ""):
    """Registra la decisión del aprobador en la etapa actual y avanza la solicitud.

    - Rechazo → estado RECHAZADA.
    - Aprobación → avanza a la siguiente etapa aplicable dentro del mismo flujo
      (departamental o general), reseteando el reloj de SLA; si no hay más,
      estado APROBADA.
    """
    from .models import FlujoAprobacion, RegistroAprobacion, SolicitudAprobacion

    solicitud = (
        SolicitudAprobacion.objects.select_for_update(of=("self",))
        .select_related("etapa_actual_flujo", "id_tipo_aprobacion")
        .get(pk=solicitud.pk)
    )
    if solicitud.estado_solicitud != PENDIENTE:
        raise AprobacionError(f"La solicitud no está pendiente (estado: {solicitud.estado_solicitud}).")

    etapa = solicitud.etapa_actual_flujo
    if etapa is None:
        raise AprobacionError("La solicitud pendiente no tiene etapa actual asignada.")

    # Authz (SEC HIGH): solo el aprobador designado (o destinatario de escalación) puede decidir.
    _verificar_aprobador(etapa, usuario, solicitud=solicitud)
    RegistroAprobacion.objects.create(
        id_solicitud_aprobacion=solicitud,
        id_flujo_aprobacion_etapa=etapa,
        id_usuario_aprobador=usuario,
        tipo_decision="APROBADO" if aprobado else "RECHAZADO",
        comentarios=comentarios,
    )

    if not aprobado:
        solicitud.estado_solicitud = RECHAZADA
        solicitud.etapa_actual_flujo = None
        solicitud.save(update_fields=["estado_solicitud", "etapa_actual_flujo"])
        return solicitud

    # Siguiente etapa aplicable (mismo tipo y ámbito departamental/general).
    qs_etapas = FlujoAprobacion.objects.filter(
        id_tipo_aprobacion=solicitud.id_tipo_aprobacion,
        activo=True,
    )
    if etapa.id_departamento_id is not None:
        qs_etapas = qs_etapas.filter(id_departamento_id=etapa.id_departamento_id)
    else:
        qs_etapas = qs_etapas.filter(id_departamento__isnull=True)

    siguientes = [
        e
        for e in qs_etapas.order_by("orden_etapa")
        if e.orden_etapa > etapa.orden_etapa and _etapa_aplica(e, solicitud.monto)
    ]
    if siguientes:
        solicitud.etapa_actual_flujo = siguientes[0]
        solicitud.estado_solicitud = PENDIENTE
        solicitud.fecha_inicio_etapa = timezone.now()
        solicitud.escalada = False
        solicitud.fecha_escalacion = None
        solicitud.save(
            update_fields=[
                "estado_solicitud",
                "etapa_actual_flujo",
                "fecha_inicio_etapa",
                "escalada",
                "fecha_escalacion",
            ]
        )
    else:
        solicitud.estado_solicitud = APROBADA
        solicitud.etapa_actual_flujo = None
        solicitud.save(update_fields=["estado_solicitud", "etapa_actual_flujo"])
    return solicitud


def _destinatarios_escalacion(etapa, empresa) -> list:
    from apps.core.models import Usuarios

    destinatarios: dict = {}
    if etapa.escalar_a_usuario_id is not None:
        usuario = (
            Usuarios.objects.filter(
                pk=etapa.escalar_a_usuario_id,
                is_active=True,
                empresas=empresa,
            )
            .distinct()
            .first()
        )
        if usuario is not None:
            destinatarios[usuario.pk] = usuario

    if etapa.escalar_a_rol_id is not None:
        for usuario in Usuarios.objects.filter(
            is_active=True,
            empresas=empresa,
            roles_asignados__id_rol=etapa.escalar_a_rol_id,
        ).distinct():
            destinatarios[usuario.pk] = usuario

    return list(destinatarios.values())


def _emitir_alertas_escalacion(solicitud, etapa, empresa) -> int:
    from apps.core.models import crear_notificacion

    destinatarios = _destinatarios_escalacion(etapa, empresa)
    if not destinatarios:
        if etapa.escalar_a_usuario_id is not None or etapa.escalar_a_rol_id is not None:
            return 0
        # Si se configuró SLA sin destinatario específico, alerta broadcast a la empresa.
        destinatarios = [None]

    emitidas = 0
    titulo = f"SLA vencido: {solicitud.id_tipo_aprobacion.nombre_tipo}"
    mensaje = (
        f"La solicitud {solicitud.nombre_modelo_origen} en etapa '{etapa.nombre_etapa}' "
        f"superó el SLA de {etapa.sla_horas} horas y fue escalada."
    )
    metadata = {
        "solicitud_id": str(solicitud.pk),
        "codigo_tipo": solicitud.id_tipo_aprobacion.codigo_tipo,
        "etapa_id": str(etapa.pk),
        "sla_horas": etapa.sla_horas,
        "escalada": True,
    }
    for dest in destinatarios:
        try:
            with transaction.atomic():
                crear_notificacion(
                    empresa=empresa,
                    titulo=titulo,
                    mensaje=mensaje,
                    tipo="ALERTA",
                    usuario=dest,
                    url_accion="/aprobaciones/solicitudes",
                    metadata=metadata,
                )
            emitidas += 1
        except Exception:  # noqa: BLE001 — notificación auxiliar no revierte escalación
            logger.warning(
                "No se pudo emitir notificación de escalación para solicitud %s",
                solicitud.pk,
                exc_info=True,
            )
    return emitidas


def escalar_solicitudes_vencidas(*, ahora=None) -> dict:
    """Evalúa solicitudes PENDIENTE con SLA vencido, aisladas por tenant bajo RLS.

    Retorna conteos de empresas procesadas, solicitudes escaladas y alertas emitidas.
    """
    from apps.core.models import Empresa

    from .models import SolicitudAprobacion

    ref_now = ahora or timezone.now()
    with rls.rls_bypass():
        empresa_ids = list(Empresa.objects.filter(activo=True).values_list("id_empresa", flat=True))

    empresas_procesadas = 0
    escaladas = 0
    alertas_emitidas = 0
    errores = 0

    for emp_id in empresa_ids:
        try:
            with rls.rls_tenant_context([emp_id]):
                with transaction.atomic():
                    candidatas = list(
                        SolicitudAprobacion.objects.select_related(
                            "etapa_actual_flujo",
                            "id_tipo_aprobacion",
                            "id_tipo_aprobacion__id_empresa",
                        )
                        .select_for_update(of=("self",))
                        .filter(
                            id_tipo_aprobacion__id_empresa_id=emp_id,
                            estado_solicitud=PENDIENTE,
                            escalada=False,
                            etapa_actual_flujo__isnull=False,
                            etapa_actual_flujo__sla_horas__isnull=False,
                        )
                        .order_by("fecha_inicio_etapa", "pk")
                    )
                    for sol in candidatas:
                        etapa = sol.etapa_actual_flujo
                        if etapa is None or etapa.sla_horas is None:
                            continue
                        inicio = sol.fecha_inicio_etapa or sol.fecha_solicitud
                        if (ref_now - inicio) < timedelta(hours=etapa.sla_horas):
                            continue
                        sol.escalada = True
                        sol.fecha_escalacion = ref_now
                        sol.save(update_fields=["escalada", "fecha_escalacion"])
                        escaladas += 1
                        alertas_emitidas += _emitir_alertas_escalacion(
                            sol,
                            etapa,
                            sol.id_tipo_aprobacion.id_empresa,
                        )
            empresas_procesadas += 1
        except Exception:  # aislamiento por tenant: un error no detiene otras empresas
            errores += 1
            logger.exception("Error escalando solicitudes vencidas para empresa %s", emp_id)

    return {
        "empresas_procesadas": empresas_procesadas,
        "escaladas": escaladas,
        "alertas_emitidas": alertas_emitidas,
        "errores": errores,
    }
