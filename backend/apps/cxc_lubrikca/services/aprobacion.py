"""Aprobación del cierre híbrido (Fase 3).

Reutiliza ``gestion_aprobaciones`` (sin duplicar lógica de SoD/authz). Una
``BandejaFacturacion`` candidata a cierre se propone para aprobación; un
aprobador del rol configurado la confirma y la bandeja pasa a ``aprobado``.
"""

from __future__ import annotations

from django.db import transaction

from apps.cxc_lubrikca.models import EstadoBandeja
from apps.cxc_lubrikca.services.captura import VinculacionError
from apps.gestion_aprobaciones import services as aprob

CODIGO_TIPO = "CXC_LUBRIKCA_CIERRE"
MODULO_ORIGEN = "cxc_lubrikca"


def _asegurar_tipo(empresa):
    """get_or_create del ``TipoAprobacion`` del cierre para la empresa."""
    from apps.gestion_aprobaciones.models import TipoAprobacion

    tipo, _ = TipoAprobacion.objects.get_or_create(
        id_empresa=empresa,
        codigo_tipo=CODIGO_TIPO,
        defaults={
            "nombre_tipo": "Cierre híbrido CxC Lubrikca",
            "modulo_origen": MODULO_ORIGEN,
            "activo": True,
        },
    )
    return tipo


@transaction.atomic
def proponer_cierre(bandeja, usuario):
    """Propone el cierre de una bandeja candidata. Devuelve la SolicitudAprobacion
    (o None si el monto no requiere aprobación según el flujo configurado)."""
    if not bandeja.candidata_a_cierre:
        raise VinculacionError(
            "La bandeja no es candidata a cierre (neto no alcanzado)."
        )
    _asegurar_tipo(bandeja.empresa)
    return aprob.crear_solicitud(
        documento=bandeja,
        empresa=bandeja.empresa,
        usuario=usuario,
        codigo_tipo=CODIGO_TIPO,
        monto=bandeja.total_motor,
    )


def _solicitud_pendiente(bandeja):
    from apps.gestion_aprobaciones.models import SolicitudAprobacion

    return SolicitudAprobacion.objects.filter(
        id_entidad_origen=bandeja.pk,
        nombre_modelo_origen=bandeja.__class__.__name__,
        estado_solicitud=aprob.PENDIENTE,
    ).first()


@transaction.atomic
def confirmar_cierre(bandeja, usuario, aprobado: bool, comentarios: str = ""):
    """Registra la decisión del aprobador sobre la solicitud pendiente de la
    bandeja. Si queda aprobada, marca la bandeja como ``aprobado``."""
    solicitud = _solicitud_pendiente(bandeja)
    if solicitud is None:
        raise VinculacionError(
            "No hay una solicitud de aprobación pendiente para esta bandeja."
        )

    solicitud = aprob.registrar_decision(
        solicitud, usuario, aprobado, comentarios=comentarios
    )

    if aprobado and aprob.esta_aprobada(bandeja):
        bandeja.estado = EstadoBandeja.APROBADO
        bandeja.aprobado_por = usuario
        bandeja.save(update_fields=["estado", "aprobado_por", "updated_at"])
    return solicitud
