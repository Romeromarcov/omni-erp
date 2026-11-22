"""Motor determinístico de recordatorios preventivos y escalación automática (ADR-015).

Porta y formaliza ``lubrikca-bots/bots/asana/escalation.py`` v4.2:
- Tareas únicas: hitos calculados por plazo total (``>=30d``, ``>=14d``, ``>=7d``, ``>=2d``, ``<=1d``).
- Regla lunes: si vence lunes y hoy es el viernes inmediato anterior (3 días antes), recuerda siempre.
- Tareas recurrentes: hitos según frecuencia (intradía/diaria → tarde; semanal → 3d,1d;
  quincenal → 7d,3d,1d; mensual → 15d,7d,3d,1d).
- Escalación progresiva de vencidas:
  * tarde del día de vencimiento (``vencida_tarde_0d``)
  * mañana del día siguiente (``vencida_manana_1d``)
  * ``escalacion_24h``, ``escalacion_48h``, ``escalacion_72h_bloqueo`` (bloquea automáticamente).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone

from apps.core.models import Notificacion

from ..models import (
    ComentarioTarea,
    EstadoTarea,
    PlantillaTareaRecurrente,
    RegistroAlertaTarea,
    SeccionProyecto,
    Tarea,
)
from .proyectos import obtener_o_crear_configuracion_seguimiento


@dataclass(frozen=True)
class AccionSeguimiento:
    clave_alerta: str
    severidad: str  # "RECORDATORIO" | "ESCALACION" | "BLOQUEO"
    escalar_lider: bool
    escalar_gerente: bool
    bloquear_tarea: bool
    mensaje: str


def _umbrales_preventivos_unica(plazo_dias: int) -> tuple[int, ...]:
    if plazo_dias >= 30:
        return (15, 7, 3, 1)
    if plazo_dias >= 14:
        return (7, 3, 1)
    if plazo_dias >= 7:
        return (3, 1)
    if plazo_dias >= 2:
        return (1,)
    return ()


def _umbrales_preventivos_recurrente(frecuencia: str) -> tuple[int, ...]:
    Frec = PlantillaTareaRecurrente.Frecuencia
    if frecuencia == Frec.MENSUAL:
        return (15, 7, 3, 1)
    if frecuencia == Frec.QUINCENAL:
        return (7, 3, 1)
    if frecuencia == Frec.SEMANAL:
        return (3, 1)
    return ()


def evaluar_alertas_tarea(
    *,
    fecha_creacion: date,
    fecha_vencimiento: date | None,
    ahora_local: datetime,
    momento: str = "AUTO",
    frecuencia_recurrente: str | None = None,
    alertas_ya_enviadas: set[str] | None = None,
    horas_bloqueo_vencida: int = 72,
    hora_tarde: time = time(15, 0),
) -> list[AccionSeguimiento]:
    """Función pura que decide qué alertas/escalaciones corresponden en ``ahora_local``.

    ``momento`` puede ser ``"MANANA"``, ``"TARDE"`` o ``"AUTO"`` (derivado de ``ahora_local``).
    """
    if fecha_vencimiento is None:
        return []

    enviadas = alertas_ya_enviadas or set()
    hoy = ahora_local.date()
    dias_restantes = (fecha_vencimiento - hoy).days
    es_tarde = momento == "TARDE" or (momento == "AUTO" and ahora_local.time() >= hora_tarde)
    es_manana = momento == "MANANA" or (momento == "AUTO" and ahora_local.time() < hora_tarde)

    acciones: list[AccionSeguimiento] = []

    # 1. Recordatorios preventivos antes del vencimiento
    if dias_restantes > 0:
        if frecuencia_recurrente:
            umbrales = _umbrales_preventivos_recurrente(frecuencia_recurrente)
        else:
            plazo_total = max((fecha_vencimiento - fecha_creacion).days, 0)
            umbrales = _umbrales_preventivos_unica(plazo_total)

        if dias_restantes in umbrales:
            clave = f"preventivo_{dias_restantes}d"
            if clave not in enviadas:
                acciones.append(
                    AccionSeguimiento(
                        clave_alerta=clave,
                        severidad="RECORDATORIO",
                        escalar_lider=False,
                        escalar_gerente=False,
                        bloquear_tarea=False,
                        mensaje=f"La tarea vence en {dias_restantes} día(s) ({fecha_vencimiento.isoformat()}).",
                    )
                )
        # Regla especial viernes -> lunes aunque el plazo sea corto (<7 días)
        elif fecha_vencimiento.weekday() == 0 and dias_restantes == 3:
            clave = "viernes_previo_lunes"
            if clave not in enviadas:
                acciones.append(
                    AccionSeguimiento(
                        clave_alerta=clave,
                        severidad="RECORDATORIO",
                        escalar_lider=False,
                        escalar_gerente=False,
                        bloquear_tarea=False,
                        mensaje=f"Recordatorio de viernes: vence el lunes ({fecha_vencimiento.isoformat()}).",
                    )
                )
        return acciones

    # 2. Día exacto de vencimiento (dias_restantes == 0)
    if dias_restantes == 0:
        plazo_total = max((fecha_vencimiento - fecha_creacion).days, 0)
        if es_tarde:
            es_corta_o_diaria = plazo_total <= 1 or frecuencia_recurrente in (
                PlantillaTareaRecurrente.Frecuencia.INTRADIA,
                PlantillaTareaRecurrente.Frecuencia.DIARIA,
            )
            clave = "recordatorio_tarde_0d" if es_corta_o_diaria else "vencida_tarde_0d"
            if clave not in enviadas:
                acciones.append(
                    AccionSeguimiento(
                        clave_alerta=clave,
                        severidad="RECORDATORIO" if es_corta_o_diaria else "ESCALACION",
                        escalar_lider=not es_corta_o_diaria,
                        escalar_gerente=False,
                        bloquear_tarea=False,
                        mensaje=f"La tarea vence hoy ({fecha_vencimiento.isoformat()}) y sigue pendiente.",
                    )
                )
        return acciones

    # 3. Tarea vencida (dias_restantes < 0)
    fin_dia_vencimiento = datetime.combine(fecha_vencimiento, time(18, 0), tzinfo=ahora_local.tzinfo)
    horas_vencida = max((ahora_local - fin_dia_vencimiento).total_seconds() / 3600.0, 0.0)

    if dias_restantes == -1 and es_manana and "vencida_manana_1d" not in enviadas:
        acciones.append(
            AccionSeguimiento(
                clave_alerta="vencida_manana_1d",
                severidad="ESCALACION",
                escalar_lider=True,
                escalar_gerente=True,
                bloquear_tarea=False,
                mensaje="Tarea vencida desde ayer; requiere atención inmediata.",
            )
        )

    for umbral_h in (24, 48):
        if horas_vencida >= umbral_h and horas_vencida < horas_bloqueo_vencida:
            clave = f"escalacion_{umbral_h}h"
            if clave not in enviadas:
                acciones.append(
                    AccionSeguimiento(
                        clave_alerta=clave,
                        severidad="ESCALACION",
                        escalar_lider=True,
                        escalar_gerente=True,
                        bloquear_tarea=False,
                        mensaje=f"Escalación {umbral_h} h: tarea vencida desde {fecha_vencimiento.isoformat()}.",
                    )
                )

    if horas_vencida >= horas_bloqueo_vencida:
        clave_bloq = f"escalacion_{horas_bloqueo_vencida}h_bloqueo"
        if clave_bloq not in enviadas:
            acciones.append(
                AccionSeguimiento(
                    clave_alerta=clave_bloq,
                    severidad="BLOQUEO",
                    escalar_lider=True,
                    escalar_gerente=True,
                    bloquear_tarea=True,
                    mensaje=(
                        f"Bloqueo automático por superar {horas_bloqueo_vencida} h vencida "
                        f"(vencía {fecha_vencimiento.isoformat()})."
                    ),
                )
            )

    return acciones


def _zona(nombre_tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(nombre_tz)
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Caracas")


@transaction.atomic
def ejecutar_seguimiento_empresa(
    empresa,
    *,
    ahora: datetime | None = None,
    momento: str = "AUTO",
) -> dict[str, Any]:
    """Evalúa todas las tareas abiertas con vencimiento de ``empresa`` y emite alertas idempotentes."""
    cfg = obtener_o_crear_configuracion_seguimiento(empresa)
    tz = _zona(cfg.zona_horaria)
    instante = (ahora or timezone.now()).astimezone(tz)

    tareas = (
        Tarea.objects.select_for_update(of=("self",))
        .filter(
            id_empresa=empresa,
            activo=True,
            fecha_vencimiento__isnull=False,
        )
        .exclude(estado__in=[EstadoTarea.COMPLETADA, EstadoTarea.CANCELADA])
        .select_related("asignado_a", "area__lider", "plantilla_recurrente")
        .prefetch_related("alertas_emitidas")
    )

    alertas_creadas = 0
    tareas_bloqueadas = 0

    for tarea in tareas:
        ya_enviadas = {a.clave_alerta for a in tarea.alertas_emitidas.all()}
        frec = (
            tarea.plantilla_recurrente.frecuencia
            if tarea.plantilla_recurrente_id and tarea.plantilla_recurrente
            else None
        )
        fecha_creacion_local = tarea.fecha_creacion.astimezone(tz).date()

        acciones = evaluar_alertas_tarea(
            fecha_creacion=fecha_creacion_local,
            fecha_vencimiento=tarea.fecha_vencimiento,
            ahora_local=instante,
            momento=momento,
            frecuencia_recurrente=frec,
            alertas_ya_enviadas=ya_enviadas,
            horas_bloqueo_vencida=cfg.horas_bloqueo_vencida,
            hora_tarde=cfg.hora_recordatorio_tarde,
        )

        for acc in acciones:
            RegistroAlertaTarea.objects.create(
                id_empresa=empresa,
                tarea=tarea,
                clave_alerta=acc.clave_alerta,
                destinatario=tarea.asignado_a or cfg.gerente,
                canal="IN_APP",
                detalle=acc.mensaje[:280],
            )
            alertas_creadas += 1

            destinatarios = []
            if tarea.asignado_a_id:
                destinatarios.append(tarea.asignado_a)
            if acc.escalar_lider and tarea.area and tarea.area.lider_id:
                if all(u.pk != tarea.area.lider_id for u in destinatarios):
                    destinatarios.append(tarea.area.lider)
            if acc.escalar_gerente and cfg.gerente_id:
                if all(u.pk != cfg.gerente_id for u in destinatarios):
                    destinatarios.append(cfg.gerente)

            tipo_notif = (
                "ERROR" if acc.bloquear_tarea else ("ADVERTENCIA" if acc.severidad == "ESCALACION" else "ALERTA")
            )
            for usuario_dest in destinatarios:
                Notificacion.objects.create(
                    id_empresa=empresa,
                    id_usuario=usuario_dest,
                    tipo=tipo_notif,
                    titulo=f"[{acc.severidad}] {tarea.titulo[:140]}",
                    mensaje=acc.mensaje,
                    url_accion=f"/tareas/{tarea.id_tarea}",
                    metadata={
                        "tarea_id": str(tarea.id_tarea),
                        "clave_alerta": acc.clave_alerta,
                    },
                )

            if acc.bloquear_tarea and not tarea.bloqueada_por_escalacion:
                tarea.estado = EstadoTarea.BLOQUEADA
                tarea.bloqueada_por_escalacion = True
                tarea.motivo_bloqueo = acc.mensaje[:280]
                campos_actualizar = [
                    "estado",
                    "bloqueada_por_escalacion",
                    "motivo_bloqueo",
                    "fecha_actualizacion",
                ]
                if tarea.proyecto_id is not None:
                    sec_bloq = (
                        SeccionProyecto.objects.filter(
                            id_empresa=empresa,
                            proyecto_id=tarea.proyecto_id,
                            estado_destino=EstadoTarea.BLOQUEADA,
                            activo=True,
                        )
                        .order_by("orden", "pk")
                        .first()
                    )
                    if sec_bloq is not None:
                        tarea.seccion = sec_bloq
                        campos_actualizar.append("seccion")
                tarea.save(update_fields=campos_actualizar)
                ComentarioTarea.objects.create(
                    id_empresa=empresa,
                    tarea=tarea,
                    autor=None,
                    autor_nombre="Motor de Escalación",
                    cuerpo=acc.mensaje,
                    es_sistema=True,
                )
                tareas_bloqueadas += 1

    return {
        "momento": momento,
        "instante": instante.isoformat(),
        "alertas_emitidas": alertas_creadas,
        "tareas_bloqueadas": tareas_bloqueadas,
    }
