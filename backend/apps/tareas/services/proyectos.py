"""Servicios de gestión de áreas, proyectos Kanban, tareas, comentarios y dependencias."""

from __future__ import annotations

import re
import unicodedata
from collections import deque
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.core.models import Notificacion, Usuarios

from ..models import (
    AreaOperativa,
    ComentarioTarea,
    ConfiguracionSeguimientoTareas,
    DependenciaTarea,
    EstadoTarea,
    MiembroAreaOperativa,
    PrioridadTarea,
    Proyecto,
    SeccionProyecto,
    Tarea,
)

SECCIONES_ESTANDAR: tuple[tuple[str, str], ...] = (
    ("Pendiente", EstadoTarea.PENDIENTE),
    ("En ejecución", EstadoTarea.EN_EJECUCION),
    ("En revisión", EstadoTarea.EN_REVISION),
    ("Completada", EstadoTarea.COMPLETADA),
    ("Bloqueada", EstadoTarea.BLOQUEADA),
)


class TareaError(Exception):
    """Error controlado de negocio del módulo de tareas."""

    def __init__(self, mensaje: str, status: int = 400):
        super().__init__(mensaje)
        self.status = status


def limpiar_texto(valor: str | None) -> str:
    return (valor or "").replace("\x00", "").strip()


def slugificar_area(nombre: str) -> str:
    normalizado = (
        unicodedata.normalize("NFKD", limpiar_texto(nombre).lower()).encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", normalizado).strip("-")
    if not slug:
        raise TareaError("El nombre del área debe contener caracteres alfanuméricos.")
    return slug[:120]


def _traducir_validacion(exc: ValidationError) -> TareaError:
    if hasattr(exc, "message_dict"):
        mensajes = "; ".join(f"{campo}: {', '.join(lista)}" for campo, lista in exc.message_dict.items())
    else:
        mensajes = "; ".join(exc.messages)
    return TareaError(mensajes or "Datos inválidos.", status=400)


def _nombre_corto_usuario(usuario: Usuarios | None) -> str:
    if usuario is None:
        return "Colaborador"
    completo = limpiar_texto(usuario.get_full_name())
    if completo:
        return completo.split()[0]
    return limpiar_texto(usuario.username) or "Colaborador"


@transaction.atomic
def crear_area_operativa(
    *,
    empresa,
    nombre: str,
    color: str = "#378ADD",
    departamento=None,
    lider: Usuarios | None = None,
    palabras_clave: list[str] | None = None,
    miembros: list[Usuarios] | None = None,
) -> AreaOperativa:
    nombre_limpio = limpiar_texto(nombre)
    if not nombre_limpio:
        raise TareaError("El nombre del área es obligatorio.")
    slug = slugificar_area(nombre_limpio)
    if AreaOperativa.objects.filter(id_empresa=empresa, slug=slug, activo=True).exists():
        raise TareaError(f"Ya existe un área activa con identificador '{slug}'.", status=409)

    claves = [limpiar_texto(k).lower() for k in (palabras_clave or []) if isinstance(k, str) and limpiar_texto(k)]
    area = AreaOperativa(
        id_empresa=empresa,
        nombre=nombre_limpio,
        slug=slug,
        color=limpiar_texto(color) or "#378ADD",
        departamento=departamento,
        lider=lider,
        palabras_clave=claves,
    )
    try:
        area.full_clean()
        area.save()
    except ValidationError as exc:
        raise _traducir_validacion(exc) from exc

    if miembros:
        sincronizar_miembros_area(empresa=empresa, area=area, usuarios=miembros)
    return area


@transaction.atomic
def sincronizar_miembros_area(
    *,
    empresa,
    area: AreaOperativa,
    usuarios: list[Usuarios],
) -> list[MiembroAreaOperativa]:
    if area.id_empresa_id != empresa.pk:
        raise TareaError("El área no pertenece a la empresa.", status=403)

    ids_objetivo = {u.pk for u in usuarios}
    for miembro in MiembroAreaOperativa.objects.filter(id_empresa=empresa, area=area, activo=True):
        if miembro.usuario_id not in ids_objetivo:
            miembro.soft_delete()

    activos: list[MiembroAreaOperativa] = []
    for usuario in usuarios:
        existente = MiembroAreaOperativa.objects.filter(id_empresa=empresa, area=area, usuario=usuario).first()
        if existente is not None:
            if not existente.activo:
                existente.restore()
            activos.append(existente)
            continue
        nuevo = MiembroAreaOperativa(id_empresa=empresa, area=area, usuario=usuario)
        try:
            nuevo.full_clean()
            nuevo.save()
        except ValidationError as exc:
            raise _traducir_validacion(exc) from exc
        activos.append(nuevo)
    return activos


@transaction.atomic
def crear_proyecto_con_secciones(
    *,
    empresa,
    nombre: str,
    descripcion: str = "",
    color: str = "#1D9E75",
    vista_predeterminada: str = Proyecto.VistaPredeterminada.TABLERO,
    es_personal: bool = False,
    area: AreaOperativa | None = None,
    propietario: Usuarios | None = None,
    secciones: list[tuple[str, str]] | None = None,
) -> Proyecto:
    nombre_limpio = limpiar_texto(nombre)
    if not nombre_limpio:
        raise TareaError("El nombre del proyecto es obligatorio.")

    proyecto = Proyecto(
        id_empresa=empresa,
        nombre=nombre_limpio,
        descripcion=limpiar_texto(descripcion),
        color=limpiar_texto(color) or "#1D9E75",
        vista_predeterminada=vista_predeterminada,
        es_personal=es_personal,
        area=area,
        propietario=propietario,
    )
    try:
        with transaction.atomic():
            proyecto.full_clean()
            proyecto.save()
    except ValidationError as exc:
        raise _traducir_validacion(exc) from exc
    except IntegrityError as exc:
        raise TareaError("Ya existe un proyecto personal activo para este usuario.", status=409) from exc

    definiciones = secciones if secciones is not None else list(SECCIONES_ESTANDAR)
    for indice, (sec_nombre, estado_dest) in enumerate(definiciones):
        sec = SeccionProyecto(
            id_empresa=empresa,
            proyecto=proyecto,
            nombre=limpiar_texto(sec_nombre),
            estado_destino=estado_dest,
            orden=indice,
        )
        try:
            sec.full_clean()
            sec.save()
        except ValidationError as exc:
            raise _traducir_validacion(exc) from exc
    return proyecto


@transaction.atomic
def asegurar_proyecto_personal(*, empresa, usuario: Usuarios) -> Proyecto:
    """Devuelve o crea de forma idempotente el tablero Kanban personal del usuario."""
    existente = (
        Proyecto.objects.filter(
            id_empresa=empresa,
            propietario=usuario,
            es_personal=True,
            activo=True,
        )
        .prefetch_related("secciones")
        .first()
    )
    if existente is not None:
        return existente

    nombre = f"Tareas - {_nombre_corto_usuario(usuario)}"
    try:
        return crear_proyecto_con_secciones(
            empresa=empresa,
            nombre=nombre,
            es_personal=True,
            propietario=usuario,
        )
    except TareaError as exc:
        if exc.status == 409:
            ganador = (
                Proyecto.objects.filter(
                    id_empresa=empresa,
                    propietario=usuario,
                    es_personal=True,
                    activo=True,
                )
                .prefetch_related("secciones")
                .first()
            )
            if ganador is not None:
                return ganador
        raise


def _resolver_seccion_inicial(
    proyecto: Proyecto | None,
    seccion: SeccionProyecto | None,
    estado: str,
) -> SeccionProyecto | None:
    if seccion is not None:
        return seccion
    if proyecto is None:
        return None
    por_estado = (
        SeccionProyecto.objects.filter(proyecto=proyecto, estado_destino=estado, activo=True)
        .order_by("orden", "pk")
        .first()
    )
    if por_estado is not None:
        return por_estado
    return SeccionProyecto.objects.filter(proyecto=proyecto, activo=True).order_by("orden", "pk").first()


@transaction.atomic
def crear_tarea(
    *,
    empresa,
    titulo: str,
    descripcion: str = "",
    estado: str = EstadoTarea.PENDIENTE,
    prioridad: str = PrioridadTarea.MEDIA,
    origen: str = Tarea.Origen.WEB,
    proyecto: Proyecto | None = None,
    seccion: SeccionProyecto | None = None,
    area: AreaOperativa | None = None,
    tarea_padre: Tarea | None = None,
    asignado_a: Usuarios | None = None,
    creado_por: Usuarios | None = None,
    fecha_inicio: date | None = None,
    fecha_vencimiento: date | None = None,
    hora_vencimiento=None,
    entidad_tipo: str = "",
    entidad_id=None,
    plantilla_recurrente=None,
    minuta_origen=None,
    idempotency_key: str = "",
    usar_tablero_personal_si_falta: bool = True,
) -> tuple[Tarea, bool]:
    """Crea una tarea (o devuelve la previa si ``idempotency_key`` ya existe).

    Retorna ``(tarea, creada)``.
    """
    titulo_limpio = limpiar_texto(titulo)
    if not titulo_limpio:
        raise TareaError("El título de la tarea es obligatorio.")

    idem = limpiar_texto(idempotency_key)[:120]
    if idem:
        previa = Tarea.objects.filter(id_empresa=empresa, idempotency_key=idem).first()
        if previa is not None:
            return previa, False

    if seccion is not None and proyecto is None:
        proyecto = seccion.proyecto
    elif proyecto is None and tarea_padre is None and asignado_a is not None and usar_tablero_personal_si_falta:
        proyecto = asegurar_proyecto_personal(empresa=empresa, usuario=asignado_a)

    if area is None and proyecto is not None and proyecto.area_id is not None:
        area = proyecto.area

    seccion_efectiva = _resolver_seccion_inicial(proyecto, seccion, estado)
    completada_en = timezone.now() if estado == EstadoTarea.COMPLETADA else None

    tarea = Tarea(
        id_empresa=empresa,
        titulo=titulo_limpio,
        descripcion=limpiar_texto(descripcion),
        estado=estado,
        prioridad=prioridad,
        origen=origen,
        proyecto=proyecto,
        seccion=seccion_efectiva,
        area=area,
        tarea_padre=tarea_padre,
        asignado_a=asignado_a,
        creado_por=creado_por,
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=fecha_vencimiento,
        hora_vencimiento=hora_vencimiento,
        completada_en=completada_en,
        entidad_tipo=limpiar_texto(entidad_tipo),
        entidad_id=entidad_id,
        plantilla_recurrente=plantilla_recurrente,
        minuta_origen=minuta_origen,
        idempotency_key=idem,
    )
    try:
        with transaction.atomic():
            tarea.full_clean()
            tarea.save()
    except ValidationError as exc:
        raise _traducir_validacion(exc) from exc
    except IntegrityError:
        if idem:
            previa = Tarea.objects.filter(id_empresa=empresa, idempotency_key=idem).first()
            if previa is not None:
                return previa, False
        raise TareaError("No se pudo registrar la tarea por conflicto de unicidad.", status=409)

    if asignado_a is not None and (creado_por is None or asignado_a.pk != creado_por.pk):
        Notificacion.objects.create(
            id_empresa=empresa,
            id_usuario=asignado_a,
            tipo="INFO",
            titulo=f"Nueva tarea asignada: {tarea.titulo[:120]}",
            mensaje=(
                f"Vencimiento: {tarea.fecha_vencimiento.isoformat()}"
                if tarea.fecha_vencimiento
                else "Sin fecha de vencimiento definida."
            ),
            url_accion=f"/tareas/{tarea.id_tarea}",
            metadata={"tarea_id": str(tarea.id_tarea), "origen": tarea.origen},
        )

    return tarea, True


@transaction.atomic
def cambiar_estado_tarea(
    *,
    tarea: Tarea,
    nuevo_estado: str,
    actor: Usuarios | None = None,
    motivo: str = "",
) -> Tarea:
    if nuevo_estado not in EstadoTarea.values:
        raise TareaError(f"Estado inválido: {nuevo_estado!r}.")

    anterior = tarea.estado
    if anterior == nuevo_estado and not motivo:
        return tarea

    tarea.estado = nuevo_estado
    if nuevo_estado == EstadoTarea.COMPLETADA:
        tarea.completada_en = timezone.now()
        tarea.bloqueada_por_escalacion = False
        tarea.motivo_bloqueo = ""
    elif nuevo_estado == EstadoTarea.BLOQUEADA:
        tarea.completada_en = None
        if motivo:
            tarea.motivo_bloqueo = limpiar_texto(motivo)[:280]
    else:
        tarea.completada_en = None
        tarea.bloqueada_por_escalacion = False
        if anterior == EstadoTarea.BLOQUEADA:
            tarea.motivo_bloqueo = ""

    if tarea.proyecto_id is not None:
        sec_match = (
            SeccionProyecto.objects.filter(
                id_empresa_id=tarea.id_empresa_id,
                proyecto_id=tarea.proyecto_id,
                estado_destino=nuevo_estado,
                activo=True,
            )
            .order_by("orden", "pk")
            .first()
        )
        if sec_match is not None:
            tarea.seccion = sec_match

    tarea.save()
    detalle_motivo = f" ({limpiar_texto(motivo)})" if limpiar_texto(motivo) else ""
    ComentarioTarea.objects.create(
        id_empresa_id=tarea.id_empresa_id,
        tarea=tarea,
        autor=actor,
        autor_nombre=_nombre_corto_usuario(actor) if actor else "Sistema",
        cuerpo=f"Estado actualizado: {anterior} → {nuevo_estado}{detalle_motivo}",
        es_sistema=True,
    )
    return tarea


@transaction.atomic
def mover_tarea(
    *,
    tarea: Tarea,
    seccion_destino: SeccionProyecto,
    orden_tablero: int | None = None,
    actor: Usuarios | None = None,
) -> Tarea:
    if seccion_destino.id_empresa_id != tarea.id_empresa_id or not seccion_destino.activo:
        raise TareaError("Sección destino no encontrada en la empresa.", status=404)

    tarea.proyecto = seccion_destino.proyecto
    tarea.seccion = seccion_destino
    if orden_tablero is not None and orden_tablero >= 0:
        tarea.orden_tablero = orden_tablero

    estado_anterior = tarea.estado
    nuevo_estado = seccion_destino.estado_destino
    tarea.estado = nuevo_estado
    if nuevo_estado == EstadoTarea.COMPLETADA:
        tarea.completada_en = timezone.now()
        tarea.bloqueada_por_escalacion = False
        tarea.motivo_bloqueo = ""
    elif estado_anterior == EstadoTarea.COMPLETADA:
        tarea.completada_en = None

    tarea.full_clean()
    tarea.save()

    ComentarioTarea.objects.create(
        id_empresa_id=tarea.id_empresa_id,
        tarea=tarea,
        autor=actor,
        autor_nombre=_nombre_corto_usuario(actor) if actor else "Sistema",
        cuerpo=f"Movida a sección '{seccion_destino.nombre}' ({nuevo_estado}).",
        es_sistema=True,
    )
    return tarea


@transaction.atomic
def agregar_comentario(
    *,
    tarea: Tarea,
    cuerpo: str,
    autor: Usuarios | None = None,
    autor_nombre: str = "",
    es_sistema: bool = False,
) -> ComentarioTarea:
    texto = limpiar_texto(cuerpo)
    if not texto:
        raise TareaError("El comentario no puede estar vacío.")
    comentario = ComentarioTarea(
        id_empresa_id=tarea.id_empresa_id,
        tarea=tarea,
        autor=autor,
        autor_nombre=limpiar_texto(autor_nombre) or (_nombre_corto_usuario(autor) if autor else "Sistema"),
        cuerpo=texto,
        es_sistema=es_sistema,
    )
    try:
        comentario.full_clean()
        comentario.save()
    except ValidationError as exc:
        raise _traducir_validacion(exc) from exc
    return comentario


def _genera_ciclo_dependencia(empresa_id, origen_id, destino_id) -> bool:
    """True si ``destino_id`` ya depende directa o transitivamente de ``origen_id``."""
    visitados = set()
    cola = deque([destino_id])
    while cola:
        actual = cola.popleft()
        if actual == origen_id:
            return True
        if actual in visitados:
            continue
        visitados.add(actual)
        siguientes = DependenciaTarea.objects.filter(
            id_empresa_id=empresa_id, tarea_id=actual, activo=True
        ).values_list("depende_de_id", flat=True)
        cola.extend(siguientes)
    return False


@transaction.atomic
def agregar_dependencia(
    *,
    empresa,
    tarea: Tarea,
    depende_de: Tarea,
) -> DependenciaTarea:
    if tarea.id_empresa_id != empresa.pk or depende_de.id_empresa_id != empresa.pk:
        raise TareaError("Ambas tareas deben pertenecer a la empresa.", status=403)
    if tarea.pk == depende_de.pk:
        raise TareaError("Una tarea no puede depender de sí misma.")
    if _genera_ciclo_dependencia(empresa.pk, tarea.pk, depende_de.pk):
        raise TareaError(
            "La dependencia crea un ciclo entre tareas.",
            status=409,
        )

    existente = DependenciaTarea.objects.filter(id_empresa=empresa, tarea=tarea, depende_de=depende_de).first()
    if existente is not None:
        if not existente.activo:
            existente.restore()
        return existente

    dep = DependenciaTarea(id_empresa=empresa, tarea=tarea, depende_de=depende_de)
    try:
        dep.full_clean()
        dep.save()
    except ValidationError as exc:
        raise _traducir_validacion(exc) from exc
    return dep


def obtener_o_crear_configuracion_seguimiento(empresa) -> ConfiguracionSeguimientoTareas:
    cfg = (
        ConfiguracionSeguimientoTareas.objects.filter(id_empresa=empresa, activo=True)
        .order_by("-fecha_creacion", "-pk")
        .first()
    )
    if cfg is not None:
        return cfg
    try:
        with transaction.atomic():
            return ConfiguracionSeguimientoTareas.objects.create(id_empresa=empresa)
    except IntegrityError:
        existente = (
            ConfiguracionSeguimientoTareas.objects.filter(id_empresa=empresa, activo=True)
            .order_by("-fecha_creacion", "-pk")
            .first()
        )
        if existente is not None:
            return existente
        raise


def resumen_ejecutivo_equipo(empresa, *, hoy: date | None = None) -> dict[str, Any]:
    """Resumen consolidado de ejecución operativa para panel web, reporte gerencial y MCP."""
    fecha_ref = hoy or timezone.localdate()
    base = Tarea.objects.filter(id_empresa=empresa, activo=True)
    abiertas = base.exclude(estado__in=[EstadoTarea.COMPLETADA, EstadoTarea.CANCELADA])

    por_estado = {fila["estado"]: fila["total"] for fila in base.values("estado").annotate(total=Count("id_tarea"))}
    vencidas = abiertas.filter(fecha_vencimiento__lt=fecha_ref).count()
    vencen_hoy = abiertas.filter(fecha_vencimiento=fecha_ref).count()
    bloqueadas_escalacion = abiertas.filter(bloqueada_por_escalacion=True).count()
    completadas_hoy = base.filter(estado=EstadoTarea.COMPLETADA, completada_en__date=fecha_ref).count()

    por_area = list(
        abiertas.values("area__id_area", "area__nombre")
        .annotate(
            abiertas=Count("id_tarea"),
            vencidas=Count("id_tarea", filter=Q(fecha_vencimiento__lt=fecha_ref)),
            bloqueadas=Count("id_tarea", filter=Q(estado=EstadoTarea.BLOQUEADA)),
        )
        .order_by("-vencidas", "-abiertas")
    )
    por_responsable = list(
        abiertas.values(
            "asignado_a__id",
            "asignado_a__username",
            "asignado_a__first_name",
            "asignado_a__last_name",
        )
        .annotate(
            abiertas=Count("id_tarea"),
            vencidas=Count("id_tarea", filter=Q(fecha_vencimiento__lt=fecha_ref)),
            bloqueadas=Count("id_tarea", filter=Q(estado=EstadoTarea.BLOQUEADA)),
        )
        .order_by("-vencidas", "-abiertas")
    )

    return {
        "fecha_corte": fecha_ref.isoformat(),
        "totales": {
            "pendientes": por_estado.get(EstadoTarea.PENDIENTE, 0),
            "en_ejecucion": por_estado.get(EstadoTarea.EN_EJECUCION, 0),
            "en_revision": por_estado.get(EstadoTarea.EN_REVISION, 0),
            "bloqueadas": por_estado.get(EstadoTarea.BLOQUEADA, 0),
            "completadas": por_estado.get(EstadoTarea.COMPLETADA, 0),
            "canceladas": por_estado.get(EstadoTarea.CANCELADA, 0),
            "abiertas": abiertas.count(),
            "vencidas": vencidas,
            "vencen_hoy": vencen_hoy,
            "bloqueadas_por_escalacion": bloqueadas_escalacion,
            "completadas_hoy": completadas_hoy,
        },
        "por_area": [
            {
                "area_id": str(item["area__id_area"]) if item["area__id_area"] else None,
                "area_nombre": item["area__nombre"] or "Sin área",
                "abiertas": item["abiertas"],
                "vencidas": item["vencidas"],
                "bloqueadas": item["bloqueadas"],
            }
            for item in por_area
        ],
        "por_responsable": [
            {
                "usuario_id": (str(item["asignado_a__id"]) if item["asignado_a__id"] else None),
                "username": item["asignado_a__username"] or "sin_asignar",
                "nombre": (
                    f"{item['asignado_a__first_name'] or ''} {item['asignado_a__last_name'] or ''}".strip()
                    or item["asignado_a__username"]
                    or "Sin asignar"
                ),
                "abiertas": item["abiertas"],
                "vencidas": item["vencidas"],
                "bloqueadas": item["bloqueadas"],
            }
            for item in por_responsable
        ],
    }
