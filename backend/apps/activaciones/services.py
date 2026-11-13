"""Lógica de negocio de activaciones: capacidad de recursos, alta/cancelación y sync a Google Calendar."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction

from .tasks import encolar_sync
from .models import (
    CalendarioActivacion,
    EventoActivacion,
    RecursoActivacion,
    UsoRecursoEvento,
)

log = logging.getLogger(__name__)


class ActivacionError(Exception):
    """Error de negocio mostrable al usuario (mensaje en español)."""


class CapacidadExcedida(ActivacionError):
    def __init__(self, mensaje: str, detalle: dict | None = None):
        super().__init__(mensaje)
        self.detalle = detalle or {}


@dataclass(frozen=True)
class Disponibilidad:
    codigo: str
    nombre: str
    capacidad: int
    pico_usado: int

    @property
    def libres(self) -> int:
        return max(self.capacidad - self.pico_usado, 0)


def _eventos_solapados(calendario, inicio, fin, excluir_evento=None):
    qs = EventoActivacion.objects.filter(
        calendario=calendario,
        estado=EventoActivacion.Estado.PROGRAMADO,
        activo=True,
        inicio__lt=fin,
        fin__gt=inicio,
    ).prefetch_related("usos")
    if excluir_evento is not None:
        qs = qs.exclude(pk=excluir_evento.pk)
    return list(qs)


def disponibilidad(
    calendario: CalendarioActivacion,
    inicio: datetime,
    fin: datetime,
    excluir_evento=None,
):
    """Por recurso: capacidad y *pico* de uso simultáneo dentro de [inicio, fin).

    El pico se evalúa en cada instante de arranque de un evento solapado (y en ``inicio``),
    no sumando todos los solapados: dos eventos que no coinciden entre sí no se acumulan.
    """
    eventos = _eventos_solapados(calendario, inicio, fin, excluir_evento)
    puntos = [inicio] + [e.inicio for e in eventos if inicio < e.inicio < fin]
    uso_por_evento = {
        e.pk: {u.recurso_id: u.cantidad for u in e.usos.all()} for e in eventos
    }
    out = []
    for r in calendario.recursos.filter(activo=True):
        pico = 0
        for t in puntos:
            usado = sum(
                uso_por_evento[e.pk].get(r.pk, 0)
                for e in eventos
                if e.inicio <= t < e.fin
            )
            pico = max(pico, usado)
        out.append(Disponibilidad(r.codigo, r.nombre, r.capacidad, pico))
    return out


def verificar_capacidad(
    calendario, inicio, fin, usos: dict[str, int], excluir_evento=None
) -> None:
    """Lanza ``CapacidadExcedida`` si ``usos`` ({codigo: cantidad}) no cabe en el horario."""
    if fin <= inicio:
        raise ActivacionError("La hora de fin debe ser posterior a la de inicio.")
    disp = {
        d.codigo: d for d in disponibilidad(calendario, inicio, fin, excluir_evento)
    }
    for codigo, cantidad in usos.items():
        if cantidad <= 0:
            continue
        d = disp.get(codigo)
        if d is None:
            raise ActivacionError(f"El recurso «{codigo}» no existe en el calendario.")
        detalle = {
            "recurso": codigo,
            "pedido": cantidad,
            "capacidad": d.capacidad,
            "libres": d.libres,
        }
        if cantidad > d.capacidad:
            raise CapacidadExcedida(
                f"Pides {cantidad} {d.nombre.lower()} pero solo existen {d.capacidad}.",
                detalle,
            )
        if cantidad > d.libres:
            raise CapacidadExcedida(
                f"No hay {d.nombre.lower()} suficientes en ese horario: quedan {d.libres} de "
                f"{d.capacidad} y pides {cantidad}.",
                detalle,
            )


def calendario_predeterminado(empresa) -> CalendarioActivacion:
    cal = CalendarioActivacion.objects.filter(
        id_empresa=empresa, activo=True, es_predeterminado=True
    ).first()
    if cal is None:
        raise ActivacionError(
            "La empresa no tiene un calendario de activaciones predeterminado."
        )
    return cal


@transaction.atomic
def crear_evento(
    *,
    empresa,
    calendario,
    cliente_nombre,
    ubicacion,
    inicio,
    fin,
    usos=None,
    cliente=None,
    vendedor=None,
    vendedor_nombre="",
    materiales=None,
    notas="",
    origen=EventoActivacion.Origen.WEB,
) -> EventoActivacion:
    """Crea un evento validando capacidad. Serializa por calendario (lock de fila) para evitar carreras."""
    cal = CalendarioActivacion.objects.select_for_update().get(
        pk=calendario.pk, id_empresa=empresa
    )
    usos = {k: int(v) for k, v in (usos or {}).items() if int(v) > 0}
    verificar_capacidad(cal, inicio, fin, usos)
    evento = EventoActivacion.objects.create(
        id_empresa=empresa,
        calendario=cal,
        cliente=cliente,
        cliente_nombre=cliente_nombre,
        vendedor=vendedor,
        vendedor_nombre=vendedor_nombre,
        ubicacion=ubicacion,
        inicio=inicio,
        fin=fin,
        materiales=materiales or [],
        notas=notas,
        origen=origen,
    )
    recursos = {
        r.codigo: r
        for r in RecursoActivacion.objects.filter(calendario=cal, activo=True)
    }
    UsoRecursoEvento.objects.bulk_create(
        [
            UsoRecursoEvento(
                id_empresa=empresa, evento=evento, recurso=recursos[c], cantidad=n
            )
            for c, n in usos.items()
        ]
    )
    transaction.on_commit(lambda: encolar_sync(evento.pk))
    return evento


@transaction.atomic
def cancelar_evento(evento: EventoActivacion) -> EventoActivacion:
    if evento.estado == EventoActivacion.Estado.CANCELADO:
        raise ActivacionError("El evento ya está cancelado.")
    evento.estado = EventoActivacion.Estado.CANCELADO
    evento.save(update_fields=["estado", "fecha_actualizacion"])
    transaction.on_commit(lambda: encolar_sync(evento.pk))
    return evento


def sincronizar_google(evento_id) -> None:
    """Refleja el evento en Google Calendar. Nunca lanza: un fallo se guarda en ``sync_error``."""
    from . import google_calendar

    evento = (
        EventoActivacion.objects.select_related("calendario")
        .prefetch_related("usos__recurso")
        .get(pk=evento_id)
    )
    if not evento.calendario.google_calendar_id or not google_calendar.configurado():
        return
    try:
        if evento.estado == EventoActivacion.Estado.CANCELADO:
            if evento.google_event_id:
                google_calendar.borrar(evento)
            return
        evento.google_event_id = google_calendar.upsert(evento)
        evento.sync_error = ""
    except Exception:  # noqa: BLE001 - el registro local ya es válido
        log.exception("Sync Google Calendar falló (evento %s)", evento_id)
        evento.sync_error = "No se pudo sincronizar con Google Calendar."
    evento.save(update_fields=["google_event_id", "sync_error", "fecha_actualizacion"])
