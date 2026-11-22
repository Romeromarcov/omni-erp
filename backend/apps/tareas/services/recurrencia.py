"""Generación determinística e idempotente de tareas recurrentes."""

from __future__ import annotations

import calendar
from datetime import date, time, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from ..models import PlantillaTareaRecurrente, Tarea
from .proyectos import TareaError, crear_tarea


def _parsear_hora(texto: str) -> time:
    partes = texto.strip().split(":")
    if len(partes) != 2:
        raise TareaError(f"Hora inválida '{texto}'; usa formato HH:MM.")
    try:
        h, m = int(partes[0]), int(partes[1])
        return time(h, m)
    except ValueError as exc:
        raise TareaError(f"Hora inválida '{texto}'; usa formato HH:MM.") from exc


def calcular_siguiente_fecha(
    *,
    frecuencia: str,
    actual: date,
    dias_semana: list[int] | None = None,
    dia_mes: int | None = None,
) -> date:
    """Calcula la próxima fecha de ejecución tras materializar ``actual``."""
    Frec = PlantillaTareaRecurrente.Frecuencia

    if frecuencia in (Frec.INTRADIA, Frec.DIARIA):
        return actual + timedelta(days=1)

    if frecuencia == Frec.SEMANAL:
        dias_validos: list[int] = []
        if isinstance(dias_semana, list):
            for raw_d in dias_semana:
                try:
                    d_int = int(raw_d)
                except (ValueError, TypeError):
                    continue
                if 0 <= d_int <= 6 and d_int not in dias_validos:
                    dias_validos.append(d_int)
        dias_validos.sort()
        if not dias_validos:
            return actual + timedelta(days=7)
        for delta in range(1, 8):
            candidato = actual + timedelta(days=delta)
            if candidato.weekday() in dias_validos:
                return candidato
        return actual + timedelta(days=7)

    if frecuencia == Frec.QUINCENAL:
        return actual + timedelta(days=14)

    if frecuencia == Frec.MENSUAL:
        objetivo_dia = dia_mes or actual.day
        anio = actual.year + (1 if actual.month == 12 else 0)
        mes = 1 if actual.month == 12 else actual.month + 1
        ultimo_dia = calendar.monthrange(anio, mes)[1]
        return date(anio, mes, min(objetivo_dia, ultimo_dia))

    raise TareaError(f"Frecuencia recurrente no soportada: {frecuencia!r}.")


@transaction.atomic
def generar_tareas_recurrentes_pendientes(
    empresa,
    *,
    fecha_hoy: date | None = None,
) -> dict[str, Any]:
    """Materializa todas las plantillas recurrentes activas vencidas hasta ``fecha_hoy``."""
    hoy = fecha_hoy or timezone.localdate()
    plantillas = (
        PlantillaTareaRecurrente.objects.select_for_update(of=("self",))
        .filter(id_empresa=empresa, activo=True, proxima_ejecucion__lte=hoy)
        .select_related("proyecto", "area", "asignado_a", "creado_por")
        .order_by("proxima_ejecucion", "pk")
    )

    creadas: list[str] = []
    omitidas_idempotencia = 0
    errores = 0
    ahora = timezone.now()

    for plantilla in plantillas:
        try:
            with transaction.atomic():
                fecha_obj = plantilla.proxima_ejecucion
                if (
                    plantilla.frecuencia == PlantillaTareaRecurrente.Frecuencia.INTRADIA
                    and isinstance(plantilla.horas_dia, list)
                    and plantilla.horas_dia
                ):
                    for raw_hora in plantilla.horas_dia:
                        hora_obj = _parsear_hora(str(raw_hora))
                        idem = f"rec:{plantilla.pk}:{fecha_obj.isoformat()}:{hora_obj.strftime('%H%M')}"
                        tarea, nueva = crear_tarea(
                            empresa=empresa,
                            titulo=plantilla.titulo,
                            descripcion=plantilla.descripcion,
                            prioridad=plantilla.prioridad,
                            origen=Tarea.Origen.RECURRENCIA,
                            proyecto=plantilla.proyecto,
                            area=plantilla.area,
                            asignado_a=plantilla.asignado_a,
                            creado_por=plantilla.creado_por,
                            fecha_inicio=fecha_obj,
                            fecha_vencimiento=fecha_obj,
                            hora_vencimiento=hora_obj,
                            plantilla_recurrente=plantilla,
                            idempotency_key=idem,
                        )
                        if nueva:
                            creadas.append(str(tarea.id_tarea))
                        else:
                            omitidas_idempotencia += 1
                else:
                    idem = f"rec:{plantilla.pk}:{fecha_obj.isoformat()}"
                    tarea, nueva = crear_tarea(
                        empresa=empresa,
                        titulo=plantilla.titulo,
                        descripcion=plantilla.descripcion,
                        prioridad=plantilla.prioridad,
                        origen=Tarea.Origen.RECURRENCIA,
                        proyecto=plantilla.proyecto,
                        area=plantilla.area,
                        asignado_a=plantilla.asignado_a,
                        creado_por=plantilla.creado_por,
                        fecha_inicio=fecha_obj,
                        fecha_vencimiento=fecha_obj,
                        plantilla_recurrente=plantilla,
                        idempotency_key=idem,
                    )
                    if nueva:
                        creadas.append(str(tarea.id_tarea))
                    else:
                        omitidas_idempotencia += 1

                siguiente = calcular_siguiente_fecha(
                    frecuencia=plantilla.frecuencia,
                    actual=fecha_obj,
                    dias_semana=plantilla.dias_semana,
                    dia_mes=plantilla.dia_mes,
                )
                while siguiente <= hoy:
                    siguiente = calcular_siguiente_fecha(
                        frecuencia=plantilla.frecuencia,
                        actual=siguiente,
                        dias_semana=plantilla.dias_semana,
                        dia_mes=plantilla.dia_mes,
                    )
                plantilla.proxima_ejecucion = siguiente
                plantilla.ultima_generacion_en = ahora
                plantilla.save(
                    update_fields=[
                        "proxima_ejecucion",
                        "ultima_generacion_en",
                        "fecha_actualizacion",
                    ]
                )
        except (TareaError, ValueError, TypeError):
            errores += 1

    return {
        "fecha": hoy.isoformat(),
        "tareas_creadas": len(creadas),
        "ids_creadas": creadas,
        "omitidas_idempotencia": omitidas_idempotencia,
        "errores": errores,
    }
