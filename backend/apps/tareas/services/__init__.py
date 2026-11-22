"""Servicios de dominio del módulo ``apps/tareas``."""

from .escalacion import ejecutar_seguimiento_empresa, evaluar_alertas_tarea
from .minutas import confirmar_minuta, crear_minuta_borrador, enriquecer_borrador_minuta
from .proyectos import (
    SECCIONES_ESTANDAR,
    TareaError,
    agregar_comentario,
    agregar_dependencia,
    asegurar_proyecto_personal,
    cambiar_estado_tarea,
    crear_area_operativa,
    crear_proyecto_con_secciones,
    crear_tarea,
    mover_tarea,
    obtener_o_crear_configuracion_seguimiento,
    resumen_ejecutivo_equipo,
    sincronizar_miembros_area,
)
from .recurrencia import calcular_siguiente_fecha, generar_tareas_recurrentes_pendientes

__all__ = [
    "SECCIONES_ESTANDAR",
    "TareaError",
    "agregar_comentario",
    "agregar_dependencia",
    "asegurar_proyecto_personal",
    "calcular_siguiente_fecha",
    "cambiar_estado_tarea",
    "confirmar_minuta",
    "crear_area_operativa",
    "crear_minuta_borrador",
    "crear_proyecto_con_secciones",
    "crear_tarea",
    "ejecutar_seguimiento_empresa",
    "enriquecer_borrador_minuta",
    "evaluar_alertas_tarea",
    "generar_tareas_recurrentes_pendientes",
    "mover_tarea",
    "obtener_o_crear_configuracion_seguimiento",
    "resumen_ejecutivo_equipo",
    "sincronizar_miembros_area",
]
