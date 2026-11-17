"""Procesamiento estructurado de minutas de reunión hacia tareas operativas (ADR-015).

Permite recibir ítems extraídos por un modelo LLM (desde web, MCP o bot de Telegram),
enriquecerlos resolviendo responsables por nombre o por área operativa y fechas relativas,
guardar el borrador para revisión humana y confirmarlo de forma atómica creando las ``Tarea``.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.core.models import Usuarios

from ..models import AreaOperativa, MinutaReunion, PrioridadTarea, Tarea
from .proyectos import TareaError, crear_tarea, limpiar_texto

_DIAS_SEMANA_ES: dict[str, int] = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}

_PISTAS_AREA_POR_DEFECTO: dict[str, tuple[str, ...]] = {
    "ventas": ("ventas", "comercial", "cotizacion", "pedido", "cliente"),
    "almacen": ("almacen", "logistica", "despacho", "inventario", "stock"),
    "cobranza": ("cobranza", "cobro", "cartera", "atencion"),
    "administracion": ("administracion", "admin", "contabilidad", "compras", "fiscal"),
    "finanzas": ("finanzas", "tesoreria", "banco", "conciliacion"),
}


def _norm(texto: str) -> str:
    limpio = (
        unicodedata.normalize("NFKD", limpiar_texto(texto).lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"\s+", " ", limpio).strip()


def resolver_fecha_humana(valor: str | None, *, hoy: date) -> date | None:
    """Interpreta YYYY-MM-DD o expresiones comunes ('hoy', 'mañana', 'en N dias', 'viernes')."""
    if not valor:
        return None
    crudo = limpiar_texto(valor)
    iso = parse_date(crudo)
    if iso is not None:
        return iso

    norm = _norm(crudo)
    if norm == "hoy":
        return hoy
    if norm in ("manana", "mañana"):
        return hoy + timedelta(days=1)
    if norm == "pasado manana":
        return hoy + timedelta(days=2)
    if norm in ("proxima semana", "siguiente semana"):
        return hoy + timedelta(days=7)

    m_dias = re.match(r"^en\s+(\d{1,3})\s+dias?$", norm)
    if m_dias:
        return hoy + timedelta(days=int(m_dias.group(1)))

    for nombre_dia, idx in _DIAS_SEMANA_ES.items():
        if nombre_dia in norm:
            delta = (idx - hoy.weekday()) % 7
            return hoy + timedelta(days=delta or 7)

    return None


def _resolver_usuario_y_area(
    *,
    empresa,
    usuarios: list[Usuarios],
    areas: list[AreaOperativa],
    asignado_a_id: str | None,
    asignado_nombre: str,
    area_slug_o_nombre: str,
    contexto_texto: str,
) -> tuple[Usuarios | None, AreaOperativa | None]:
    usuario_resuelto: Usuarios | None = None
    area_resuelta: AreaOperativa | None = None

    if asignado_a_id:
        try:
            uid = uuid.UUID(str(asignado_a_id))
            usuario_resuelto = next((u for u in usuarios if u.pk == uid), None)
        except (ValueError, TypeError):
            usuario_resuelto = None

    if usuario_resuelto is None and asignado_nombre:
        buscado = _norm(asignado_nombre)
        for u in usuarios:
            candidatos = {
                _norm(u.username),
                _norm(u.get_full_name()),
                _norm(u.first_name),
            }
            if buscado and buscado in candidatos:
                usuario_resuelto = u
                break
        if usuario_resuelto is None and buscado:
            for u in usuarios:
                completo = _norm(u.get_full_name())
                if completo and (completo.startswith(buscado) or buscado in completo.split()):
                    usuario_resuelto = u
                    break

    texto_pistas = f"{_norm(area_slug_o_nombre)} {_norm(contexto_texto)}".strip()
    if area_slug_o_nombre:
        objetivo_area = _norm(area_slug_o_nombre)
        for a in areas:
            if objetivo_area in {_norm(a.slug), _norm(a.nombre)}:
                area_resuelta = a
                break

    if area_resuelta is None and texto_pistas:
        tokens = set(re.findall(r"[a-z0-9]+", texto_pistas))
        for a in areas:
            claves_area = {_norm(k) for k in (a.palabras_clave or []) if k}
            slug_base = _norm(a.slug).replace("-", "")
            for clave_def, sinonimos in _PISTAS_AREA_POR_DEFECTO.items():
                if clave_def in slug_base or clave_def in _norm(a.nombre):
                    claves_area.update(sinonimos)
            if claves_area & tokens:
                area_resuelta = a
                break

    if usuario_resuelto is None and area_resuelta is not None:
        if area_resuelta.lider_id:
            usuario_resuelto = area_resuelta.lider
        else:
            primera_membresia = (
                area_resuelta.miembros.filter(activo=True)
                .select_related("usuario")
                .first()
            )
            if primera_membresia is not None:
                usuario_resuelto = primera_membresia.usuario

    return usuario_resuelto, area_resuelta


def enriquecer_borrador_minuta(
    empresa,
    items: list[dict[str, Any]],
    *,
    fecha_referencia: date | None = None,
) -> list[dict[str, Any]]:
    """Normaliza y enriquece cada ítem de borrador resolviendo usuarios, áreas y fechas de la empresa."""
    hoy = fecha_referencia or timezone.localdate()
    usuarios = list(
        Usuarios.objects.filter(empresas=empresa, is_active=True).order_by("first_name", "username")
    )
    areas = list(
        AreaOperativa.objects.filter(id_empresa=empresa, activo=True)
        .select_related("lider")
        .prefetch_related("miembros__usuario")
    )

    enriquecidos: list[dict[str, Any]] = []
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        titulo = limpiar_texto(str(raw.get("titulo") or raw.get("task_name") or ""))
        if not titulo:
            continue
        descripcion = limpiar_texto(str(raw.get("descripcion") or raw.get("notes") or ""))
        asignado_nombre = limpiar_texto(
            str(raw.get("asignado_nombre") or raw.get("assignee_name") or "")
        )
        area_hint = limpiar_texto(str(raw.get("area") or ""))
        prioridad = str(raw.get("prioridad") or PrioridadTarea.MEDIA).upper()
        if prioridad not in PrioridadTarea.values:
            prioridad = PrioridadTarea.MEDIA

        fecha_raw = raw.get("fecha_vencimiento") or raw.get("due_on")
        fecha_resuelta = (
            fecha_raw
            if isinstance(fecha_raw, date)
            else resolver_fecha_humana(str(fecha_raw) if fecha_raw else None, hoy=hoy)
        )

        usuario, area = _resolver_usuario_y_area(
            empresa=empresa,
            usuarios=usuarios,
            areas=areas,
            asignado_a_id=raw.get("asignado_a_id"),
            asignado_nombre=asignado_nombre,
            area_slug_o_nombre=area_hint,
            contexto_texto=f"{titulo} {descripcion}",
        )

        faltan: list[str] = []
        if usuario is None:
            faltan.append("asignado_a")
        if fecha_resuelta is None:
            faltan.append("fecha_vencimiento")

        enriquecidos.append(
            {
                "indice": idx,
                "titulo": titulo[:240],
                "descripcion": descripcion,
                "prioridad": prioridad,
                "asignado_a_id": str(usuario.pk) if usuario else None,
                "asignado_nombre": (
                    usuario.get_full_name().strip() or usuario.username
                    if usuario
                    else asignado_nombre
                ),
                "area_id": str(area.pk) if area else None,
                "area_nombre": area.nombre if area else "",
                "fecha_vencimiento": fecha_resuelta.isoformat() if fecha_resuelta else None,
                "incompleto": faltan,
            }
        )

    return enriquecidos


@transaction.atomic
def crear_minuta_borrador(
    *,
    empresa,
    titulo: str,
    fecha_reunion: date | None = None,
    texto_fuente: str = "",
    documento_adjunto=None,
    items_propuestos: list[dict[str, Any]] | None = None,
    creado_por: Usuarios | None = None,
) -> MinutaReunion:
    titulo_limpio = limpiar_texto(titulo)
    if not titulo_limpio:
        raise TareaError("El título de la minuta es obligatorio.")

    fecha_ef = fecha_reunion or timezone.localdate()
    borrador = enriquecer_borrador_minuta(
        empresa,
        items_propuestos or [],
        fecha_referencia=fecha_ef,
    )
    minuta = MinutaReunion(
        id_empresa=empresa,
        titulo=titulo_limpio,
        fecha_reunion=fecha_ef,
        texto_fuente=limpiar_texto(texto_fuente),
        documento_adjunto=documento_adjunto,
        borrador_tareas=borrador,
        estado=MinutaReunion.Estado.BORRADOR,
        creado_por=creado_por,
    )
    minuta.full_clean()
    minuta.save()
    return minuta


@transaction.atomic
def confirmar_minuta(
    *,
    minuta: MinutaReunion,
    items_confirmados: list[dict[str, Any]] | None = None,
    actor: Usuarios | None = None,
    proyecto=None,
) -> list[Tarea]:
    """Materializa el borrador de ``minuta`` en instancias reales de ``Tarea``."""
    empresa = minuta.id_empresa
    if minuta.estado == MinutaReunion.Estado.DESCARTADA:
        raise TareaError("No se puede confirmar una minuta descartada.", status=409)
    if minuta.estado == MinutaReunion.Estado.CONFIRMADA:
        return list(
            Tarea.objects.filter(
                id_empresa=empresa, minuta_origen=minuta, activo=True
            ).order_by("fecha_creacion", "pk")
        )

    fuente_items = (
        enriquecer_borrador_minuta(
            empresa, items_confirmados, fecha_referencia=minuta.fecha_reunion
        )
        if items_confirmados is not None
        else list(minuta.borrador_tareas or [])
    )
    if not fuente_items:
        raise TareaError("La minuta no contiene tareas para confirmar.")

    usuarios_map = {
        str(u.pk): u
        for u in Usuarios.objects.filter(empresas=empresa, is_active=True)
    }
    areas_map = {
        str(a.pk): a
        for a in AreaOperativa.objects.filter(id_empresa=empresa, activo=True)
    }

    creadas: list[Tarea] = []
    for idx, item in enumerate(fuente_items):
        titulo_item = limpiar_texto(str(item.get("titulo") or ""))
        if not titulo_item:
            continue
        usuario = usuarios_map.get(str(item.get("asignado_a_id") or ""))
        area = areas_map.get(str(item.get("area_id") or ""))
        fecha_venc = (
            parse_date(str(item["fecha_vencimiento"]))
            if item.get("fecha_vencimiento")
            else None
        )
        prioridad = str(item.get("prioridad") or PrioridadTarea.MEDIA).upper()
        if prioridad not in PrioridadTarea.values:
            prioridad = PrioridadTarea.MEDIA

        tarea, _ = crear_tarea(
            empresa=empresa,
            titulo=titulo_item,
            descripcion=limpiar_texto(str(item.get("descripcion") or "")),
            prioridad=prioridad,
            origen=Tarea.Origen.MINUTA_IA,
            proyecto=proyecto,
            area=area,
            asignado_a=usuario,
            creado_por=actor or minuta.creado_por,
            fecha_vencimiento=fecha_venc,
            minuta_origen=minuta,
            idempotency_key=f"minuta:{minuta.pk}:{idx}",
        )
        creadas.append(tarea)

    if not creadas:
        raise TareaError("Ningún ítem del borrador tenía título válido.")

    minuta.borrador_tareas = fuente_items
    minuta.estado = MinutaReunion.Estado.CONFIRMADA
    minuta.confirmada_en = timezone.now()
    minuta.save(
        update_fields=["borrador_tareas", "estado", "confirmada_en", "fecha_actualizacion"]
    )
    return creadas
