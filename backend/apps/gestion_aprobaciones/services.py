"""
Lógica de negocio de aprobaciones configurables por tenant y por monto.

Una ``TipoAprobacion`` (por empresa, ``codigo_tipo`` p. ej. ORDEN_COMPRA / GASTO)
agrupa etapas ``FlujoAprobacion`` con rangos de monto (``monto_minimo`` /
``monto_maximo``) y un aprobador (rol o usuario). Cuando un documento supera el
umbral, se crea una ``SolicitudAprobacion`` que un aprobador resuelve etapa por
etapa (``RegistroAprobacion``). El documento solo avanza cuando la solicitud
queda ``APROBADA``.

Funciones públicas:
  evaluar_etapas()        — etapas aplicables a un (empresa, tipo, monto)
  requiere_aprobacion()   — ¿hay alguna etapa aplicable?
  crear_solicitud()       — crea (o devuelve) la solicitud PENDIENTE del documento
  registrar_decision()    — registra una decisión y avanza/cierra la solicitud
  esta_aprobada()         — ¿el documento tiene una solicitud APROBADA?
"""

from decimal import Decimal

from django.db import transaction

PENDIENTE = "PENDIENTE"
APROBADA = "APROBADA"
RECHAZADA = "RECHAZADA"


class AprobacionError(Exception):
    pass


def _verificar_aprobador(etapa, usuario) -> None:
    """Verifica que ``usuario`` sea el aprobador designado de la etapa (SoD/authz).

    - Si la etapa fija ``id_usuario_aprobador``: debe ser ese usuario exacto.
    - Si fija ``rol_aprobador``: el usuario debe tener ese rol (``UsuarioRoles``).
    - Si no fija ninguno: etapa abierta — cualquier usuario del tenant puede
      decidir (el control de identidad depende de que el admin configure
      aprobador o rol en la regla).
    """
    if etapa.id_usuario_aprobador_id is not None:
        if etapa.id_usuario_aprobador_id != usuario.pk:
            raise AprobacionError("No es el aprobador designado para esta etapa.")
        return
    if etapa.rol_aprobador_id is not None:
        from apps.core.models import UsuarioRoles

        if not UsuarioRoles.objects.filter(
            id_usuario=usuario, id_rol=etapa.rol_aprobador_id
        ).exists():
            raise AprobacionError("No posee el rol aprobador requerido para esta etapa.")


def _etapa_aplica(etapa, monto: Decimal) -> bool:
    """True si ``monto`` cae dentro del rango [monto_minimo, monto_maximo] de la
    etapa. Los límites nulos se interpretan como abiertos (sin tope)."""
    if etapa.monto_minimo is not None and monto < etapa.monto_minimo:
        return False
    if etapa.monto_maximo is not None and monto > etapa.monto_maximo:
        return False
    return True


def evaluar_etapas(empresa, codigo_tipo: str, monto) -> list:
    """Devuelve las etapas de flujo aplicables (activas, con el monto en rango),
    ordenadas por ``orden_etapa``. Vacío si no hay TipoAprobacion activo o ninguna
    etapa aplica → el documento no requiere aprobación."""
    from .models import FlujoAprobacion, TipoAprobacion

    monto = Decimal(str(monto))
    tipo = TipoAprobacion.objects.filter(
        id_empresa=empresa, codigo_tipo=codigo_tipo, activo=True
    ).first()
    if tipo is None:
        return []
    etapas = FlujoAprobacion.objects.filter(
        id_tipo_aprobacion=tipo, activo=True
    ).order_by("orden_etapa")
    return [e for e in etapas if _etapa_aplica(e, monto)]


def requiere_aprobacion(empresa, codigo_tipo: str, monto) -> bool:
    return bool(evaluar_etapas(empresa, codigo_tipo, monto))


def esta_aprobada(documento) -> bool:
    """True si el documento tiene una SolicitudAprobacion en estado APROBADA."""
    from .models import SolicitudAprobacion

    return SolicitudAprobacion.objects.filter(
        id_entidad_origen=documento.pk,
        nombre_modelo_origen=documento.__class__.__name__,
        estado_solicitud=APROBADA,
    ).exists()


def _solicitud_abierta(documento):
    from .models import SolicitudAprobacion

    return SolicitudAprobacion.objects.filter(
        id_entidad_origen=documento.pk,
        nombre_modelo_origen=documento.__class__.__name__,
        estado_solicitud=PENDIENTE,
    ).first()


@transaction.atomic
def crear_solicitud(documento, empresa, usuario, codigo_tipo: str, monto):
    """Crea la SolicitudAprobacion PENDIENTE del documento (idempotente: si ya hay
    una abierta, la devuelve). Devuelve None si el monto no requiere aprobación."""
    from .models import SolicitudAprobacion

    etapas = evaluar_etapas(empresa, codigo_tipo, monto)
    if not etapas:
        return None

    abierta = _solicitud_abierta(documento)
    if abierta is not None:
        return abierta

    return SolicitudAprobacion.objects.create(
        id_tipo_aprobacion=etapas[0].id_tipo_aprobacion,
        id_entidad_origen=documento.pk,
        nombre_modelo_origen=documento.__class__.__name__,
        id_usuario_solicitante=usuario,
        estado_solicitud=PENDIENTE,
        etapa_actual_flujo=etapas[0],
        monto=Decimal(str(monto)),
    )


@transaction.atomic
def registrar_decision(solicitud, usuario, aprobado: bool, comentarios: str = ""):
    """Registra la decisión del aprobador en la etapa actual y avanza la solicitud.

    - Rechazo → estado RECHAZADA (el documento se queda en borrador).
    - Aprobación → avanza a la siguiente etapa aplicable; si no hay más,
      estado APROBADA.
    """
    from .models import FlujoAprobacion, RegistroAprobacion, SolicitudAprobacion

    solicitud = SolicitudAprobacion.objects.select_for_update().get(pk=solicitud.pk)
    if solicitud.estado_solicitud != PENDIENTE:
        raise AprobacionError(
            f"La solicitud no está pendiente (estado: {solicitud.estado_solicitud})."
        )

    etapa = solicitud.etapa_actual_flujo
    # Authz (SEC HIGH): solo el aprobador designado de la etapa puede decidir.
    _verificar_aprobador(etapa, usuario)
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

    # Siguiente etapa aplicable (mismo tipo, activa, monto en rango, orden mayor).
    siguientes = [
        e
        for e in FlujoAprobacion.objects.filter(
            id_tipo_aprobacion=solicitud.id_tipo_aprobacion, activo=True
        ).order_by("orden_etapa")
        if e.orden_etapa > etapa.orden_etapa and _etapa_aplica(e, solicitud.monto)
    ]
    if siguientes:
        solicitud.etapa_actual_flujo = siguientes[0]
        solicitud.estado_solicitud = PENDIENTE
    else:
        solicitud.estado_solicitud = APROBADA
        solicitud.etapa_actual_flujo = None
    solicitud.save(update_fields=["estado_solicitud", "etapa_actual_flujo"])
    return solicitud
