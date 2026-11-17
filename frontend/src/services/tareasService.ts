/**
 * Servicio del módulo de Tareas y Proyectos Operativos (`/api/tareas/`).
 *
 * Reemplazo nativo multi-tenant de Asana (ADR-015): áreas operativas, tableros
 * Kanban y personales, tareas con subtareas/dependencias/comentarios y vínculo
 * transversal con entidades del ERP, recurrencia, minutas con IA y motor de
 * seguimiento/escalación.
 *
 * Cada payload aplica whitelist explícita de campos (CWE-915) y cero `any` (R-CODE-3).
 */
import { get, post, patch, del } from './api';
import { toList } from '../utils/api';

// ── Enumeraciones y constantes de dominio ────────────────────────────────────

export type EstadoTarea =
  | 'PENDIENTE'
  | 'EN_EJECUCION'
  | 'EN_REVISION'
  | 'BLOQUEADA'
  | 'COMPLETADA'
  | 'CANCELADA';

export const ESTADOS_TAREA: readonly EstadoTarea[] = [
  'PENDIENTE',
  'EN_EJECUCION',
  'EN_REVISION',
  'BLOQUEADA',
  'COMPLETADA',
  'CANCELADA',
] as const;

export type PrioridadTarea = 'BAJA' | 'MEDIA' | 'ALTA' | 'URGENTE';

export const PRIORIDADES_TAREA: readonly PrioridadTarea[] = [
  'BAJA',
  'MEDIA',
  'ALTA',
  'URGENTE',
] as const;

export type OrigenTarea = 'WEB' | 'BOT' | 'RECURRENTE' | 'MINUTA_IA' | 'AGENTE_IA' | 'SISTEMA';

export type FrecuenciaRecurrente = 'INTRADIA' | 'DIARIA' | 'SEMANAL' | 'QUINCENAL' | 'MENSUAL';

export const FRECUENCIAS_RECURRENTES: readonly FrecuenciaRecurrente[] = [
  'INTRADIA',
  'DIARIA',
  'SEMANAL',
  'QUINCENAL',
  'MENSUAL',
] as const;

export type EstadoMinuta = 'BORRADOR' | 'CONFIRMADA' | 'DESCARTADA';

export type MomentoSeguimiento = 'AUTO' | 'MANANA' | 'TARDE';

// ── Interfaces espejo de los serializers DRF ─────────────────────────────────

export interface MiembroAreaOperativa {
  id_miembro_area: string;
  id_empresa: string;
  area: string;
  usuario: string;
  usuario_username: string;
  usuario_nombre: string;
  activo: boolean;
  fecha_creacion: string;
}

export interface AreaOperativa {
  id_area: string;
  id_empresa: string;
  nombre: string;
  slug: string;
  color: string;
  departamento: string | null;
  lider: string | null;
  lider_nombre: string;
  palabras_clave: string[];
  miembros: MiembroAreaOperativa[];
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface SeccionProyecto {
  id_seccion: string;
  id_empresa: string;
  proyecto: string;
  nombre: string;
  estado_destino: EstadoTarea | '';
  orden: number;
  activo: boolean;
}

export interface Proyecto {
  id_proyecto: string;
  id_empresa: string;
  nombre: string;
  descripcion: string;
  color: string;
  vista_predeterminada: 'TABLERO' | 'LISTA';
  es_personal: boolean;
  archivado: boolean;
  area: string | null;
  area_nombre: string;
  propietario: string | null;
  propietario_nombre: string;
  secciones: SeccionProyecto[];
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface Tarea {
  id_tarea: string;
  id_empresa: string;
  titulo: string;
  descripcion: string;
  estado: EstadoTarea;
  prioridad: PrioridadTarea;
  origen: OrigenTarea;
  proyecto: string | null;
  proyecto_nombre: string;
  seccion: string | null;
  seccion_nombre: string;
  area: string | null;
  area_nombre: string;
  tarea_padre: string | null;
  asignado_a: string | null;
  asignado_nombre: string;
  creado_por: string | null;
  fecha_inicio: string | null;
  fecha_vencimiento: string | null;
  hora_vencimiento: string | null;
  completada_en: string | null;
  bloqueada_por_escalacion: boolean;
  motivo_bloqueo: string;
  entidad_tipo: string;
  entidad_id: string | null;
  plantilla_recurrente: string | null;
  minuta_origen: string | null;
  idempotency_key: string;
  orden_tablero: number;
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface ComentarioTarea {
  id_comentario: string;
  id_empresa: string;
  tarea: string;
  autor: string | null;
  autor_nombre: string;
  cuerpo: string;
  es_sistema: boolean;
  fecha_creacion: string;
}

export interface DependenciaTarea {
  id_dependencia: string;
  id_empresa: string;
  tarea: string;
  depende_de: string;
  depende_de_titulo: string;
  depende_de_estado: EstadoTarea;
  activo: boolean;
  fecha_creacion: string;
}

export interface PlantillaTareaRecurrente {
  id_plantilla_recurrente: string;
  id_empresa: string;
  titulo: string;
  descripcion: string;
  prioridad: PrioridadTarea;
  frecuencia: FrecuenciaRecurrente;
  dias_semana: number[];
  dia_mes: number | null;
  horas_dia: string[];
  proxima_ejecucion: string;
  ultima_generacion_en: string | null;
  proyecto: string | null;
  area: string | null;
  asignado_a: string | null;
  asignado_nombre: string;
  creado_por: string | null;
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface ItemBorradorMinuta {
  titulo: string;
  descripcion?: string;
  prioridad?: PrioridadTarea;
  asignado_a_id?: string | null;
  asignado_nombre?: string;
  area_id?: string | null;
  area?: string;
  fecha_vencimiento?: string | null;
}

export interface MinutaReunion {
  id_minuta: string;
  id_empresa: string;
  titulo: string;
  fecha_reunion: string | null;
  texto_fuente: string;
  documento_adjunto: string | null;
  borrador_tareas: ItemBorradorMinuta[];
  estado: EstadoMinuta;
  creado_por: string | null;
  confirmada_en: string | null;
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface ConfiguracionSeguimientoTareas {
  id_config_seguimiento: string;
  id_empresa: string;
  zona_horaria: string;
  hora_recordatorio_manana: string;
  hora_recordatorio_tarde: string;
  hora_reporte_gerencial: string;
  horas_bloqueo_vencida: number;
  gerente: string | null;
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface ResumenPorArea {
  area_id: string | null;
  area_nombre: string;
  abiertas: number;
  vencidas: number;
  bloqueadas: number;
}

export interface ResumenPorResponsable {
  usuario_id: string | null;
  username: string;
  nombre: string;
  abiertas: number;
  vencidas: number;
  bloqueadas: number;
}

export interface ResumenEjecutivoTareas {
  fecha_corte: string;
  totales: {
    pendientes: number;
    en_ejecucion: number;
    en_revision: number;
    bloqueadas: number;
    completadas: number;
    canceladas: number;
    abiertas: number;
    vencidas: number;
    vencen_hoy: number;
    bloqueadas_por_escalacion: number;
    completadas_hoy: number;
  };
  por_area: ResumenPorArea[];
  por_responsable: ResumenPorResponsable[];
}

export interface ResultadoMaterializacionRecurrente {
  fecha: string;
  tareas_creadas: number;
  ids_creadas: string[];
  omitidas_idempotencia: number;
  errores: number;
}

export interface ResultadoSeguimientoTareas {
  momento: string;
  recordatorios_preventivos: number;
  escalaciones_vencidas: number;
  bloqueadas_automaticamente: number;
  recurrentes_creadas: number;
}

// ── Payloads de entrada (whitelist explícita) ────────────────────────────────

export interface AreaPayload {
  nombre: string;
  color?: string;
  lider?: string | null;
  palabras_clave?: string[];
}

export interface ProyectoPayload {
  nombre: string;
  descripcion?: string;
  color?: string;
  vista_predeterminada?: 'TABLERO' | 'LISTA';
  area?: string | null;
  propietario?: string | null;
}

export interface TareaPayload {
  titulo: string;
  descripcion?: string;
  estado?: EstadoTarea;
  prioridad?: PrioridadTarea;
  proyecto?: string | null;
  seccion?: string | null;
  area?: string | null;
  tarea_padre?: string | null;
  asignado_a?: string | null;
  fecha_inicio?: string | null;
  fecha_vencimiento?: string | null;
  entidad_tipo?: string;
  entidad_id?: string | null;
}

export interface FiltroTareas {
  proyecto?: string;
  estado?: EstadoTarea | '';
  prioridad?: PrioridadTarea | '';
  area?: string;
  asignado_a?: string;
  vencidas?: boolean;
  search?: string;
}

export interface PlantillaRecurrentePayload {
  titulo: string;
  descripcion?: string;
  prioridad?: PrioridadTarea;
  frecuencia: FrecuenciaRecurrente;
  dias_semana?: number[];
  dia_mes?: number | null;
  horas_dia?: string[];
  proxima_ejecucion: string;
  proyecto?: string | null;
  area?: string | null;
  asignado_a?: string | null;
}

export interface MinutaPayload {
  titulo: string;
  fecha_reunion?: string | null;
  texto_fuente?: string;
  items_propuestos: ItemBorradorMinuta[];
}

export interface ConfiguracionSeguimientoPayload {
  zona_horaria?: string;
  hora_recordatorio_manana?: string;
  hora_recordatorio_tarde?: string;
  hora_reporte_gerencial?: string;
  horas_bloqueo_vencida?: number;
  gerente?: string | null;
}

const BASE = '/tareas';

function armarQuery(params: Record<string, string | undefined>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v) qs.set(k, v);
  }
  const s = qs.toString();
  return s ? `?${s}` : '';
}

// ── Áreas Operativas ─────────────────────────────────────────────────────────

export const areasTareasService = {
  getAll: async (): Promise<AreaOperativa[]> =>
    toList<AreaOperativa>(await get<unknown>(`${BASE}/areas/`)),

  create: (p: AreaPayload): Promise<AreaOperativa> => {
    const body: Record<string, unknown> = {
      nombre: p.nombre,
      color: p.color ?? '#378ADD',
      palabras_clave: p.palabras_clave ?? [],
    };
    if (p.lider) body.lider = p.lider;
    return post<AreaOperativa>(`${BASE}/areas/`, body);
  },

  sincronizarMiembros: (areaId: string, usuarios: string[]): Promise<AreaOperativa> =>
    post<AreaOperativa>(`${BASE}/areas/${areaId}/miembros/`, { usuarios }),

  remove: (id: string): Promise<void> => del<void>(`${BASE}/areas/${id}/`),
};

// ── Proyectos y Secciones Kanban ─────────────────────────────────────────────

export const proyectosTareasService = {
  getAll: async (archivado?: boolean): Promise<Proyecto[]> =>
    toList<Proyecto>(
      await get<unknown>(
        `${BASE}/proyectos/${armarQuery({
          archivado: archivado === undefined ? undefined : String(archivado),
        })}`,
      ),
    ),

  create: (p: ProyectoPayload): Promise<Proyecto> => {
    const body: Record<string, unknown> = {
      nombre: p.nombre,
      descripcion: p.descripcion ?? '',
      color: p.color ?? '#1D9E75',
      vista_predeterminada: p.vista_predeterminada ?? 'TABLERO',
    };
    if (p.area) body.area = p.area;
    if (p.propietario) body.propietario = p.propietario;
    return post<Proyecto>(`${BASE}/proyectos/`, body);
  },

  miTablero: (usuarioId?: string): Promise<Proyecto> =>
    post<Proyecto>(`${BASE}/proyectos/mi-tablero/`, usuarioId ? { usuario: usuarioId } : {}),

  remove: (id: string): Promise<void> => del<void>(`${BASE}/proyectos/${id}/`),
};

export const seccionesTareasService = {
  getPorProyecto: async (proyectoId: string): Promise<SeccionProyecto[]> =>
    toList<SeccionProyecto>(
      await get<unknown>(`${BASE}/secciones/${armarQuery({ proyecto: proyectoId })}`),
    ),

  create: (proyecto: string, nombre: string, orden?: number): Promise<SeccionProyecto> =>
    post<SeccionProyecto>(`${BASE}/secciones/`, {
      proyecto,
      nombre,
      orden: orden ?? 10,
    }),
};

// ── Tareas Operativas ────────────────────────────────────────────────────────

export const tareasService = {
  getAll: async (f: FiltroTareas = {}): Promise<Tarea[]> =>
    toList<Tarea>(
      await get<unknown>(
        `${BASE}/items/${armarQuery({
          proyecto: f.proyecto || undefined,
          estado: f.estado || undefined,
          prioridad: f.prioridad || undefined,
          area: f.area || undefined,
          asignado_a: f.asignado_a || undefined,
          vencidas: f.vencidas ? 'true' : undefined,
          search: f.search || undefined,
        })}`,
      ),
    ),

  getById: (id: string): Promise<Tarea> => get<Tarea>(`${BASE}/items/${id}/`),

  create: (p: TareaPayload): Promise<Tarea> => {
    const body: Record<string, unknown> = {
      titulo: p.titulo,
      descripcion: p.descripcion ?? '',
      prioridad: p.prioridad ?? 'MEDIA',
    };
    if (p.estado) body.estado = p.estado;
    if (p.proyecto) body.proyecto = p.proyecto;
    if (p.seccion) body.seccion = p.seccion;
    if (p.area) body.area = p.area;
    if (p.tarea_padre) body.tarea_padre = p.tarea_padre;
    if (p.asignado_a) body.asignado_a = p.asignado_a;
    if (p.fecha_inicio) body.fecha_inicio = p.fecha_inicio;
    if (p.fecha_vencimiento) body.fecha_vencimiento = p.fecha_vencimiento;
    if (p.entidad_tipo) body.entidad_tipo = p.entidad_tipo;
    if (p.entidad_id) body.entidad_id = p.entidad_id;
    return post<Tarea>(`${BASE}/items/`, body);
  },

  update: (id: string, p: Partial<TareaPayload>): Promise<Tarea> => {
    const body: Record<string, unknown> = {};
    if (p.titulo !== undefined) body.titulo = p.titulo;
    if (p.descripcion !== undefined) body.descripcion = p.descripcion;
    if (p.prioridad !== undefined) body.prioridad = p.prioridad;
    if (p.area !== undefined) body.area = p.area;
    if (p.asignado_a !== undefined) body.asignado_a = p.asignado_a;
    if (p.fecha_inicio !== undefined) body.fecha_inicio = p.fecha_inicio;
    if (p.fecha_vencimiento !== undefined) body.fecha_vencimiento = p.fecha_vencimiento;
    return patch<Tarea>(`${BASE}/items/${id}/`, body);
  },

  cambiarEstado: (id: string, estado: EstadoTarea, motivo = ''): Promise<Tarea> =>
    post<Tarea>(`${BASE}/items/${id}/estado/`, { estado, motivo }),

  mover: (id: string, seccion: string, ordenTablero?: number): Promise<Tarea> => {
    const body: Record<string, unknown> = { seccion };
    if (ordenTablero !== undefined) body.orden_tablero = ordenTablero;
    return post<Tarea>(`${BASE}/items/${id}/mover/`, body);
  },

  remove: (id: string): Promise<void> => del<void>(`${BASE}/items/${id}/`),

  listarComentarios: async (tareaId: string): Promise<ComentarioTarea[]> =>
    toList<ComentarioTarea>(await get<unknown>(`${BASE}/items/${tareaId}/comentarios/`)),

  agregarComentario: (tareaId: string, cuerpo: string): Promise<ComentarioTarea> =>
    post<ComentarioTarea>(`${BASE}/items/${tareaId}/comentarios/`, { cuerpo }),

  listarDependencias: async (tareaId: string): Promise<DependenciaTarea[]> =>
    toList<DependenciaTarea>(await get<unknown>(`${BASE}/items/${tareaId}/dependencias/`)),

  agregarDependencia: (tareaId: string, dependeDe: string): Promise<DependenciaTarea> =>
    post<DependenciaTarea>(`${BASE}/items/${tareaId}/dependencias/`, { depende_de: dependeDe }),
};

// ── Plantillas Recurrentes y Minutas con IA ──────────────────────────────────

export const recurrentesTareasService = {
  getAll: async (): Promise<PlantillaTareaRecurrente[]> =>
    toList<PlantillaTareaRecurrente>(await get<unknown>(`${BASE}/recurrentes/`)),

  create: (p: PlantillaRecurrentePayload): Promise<PlantillaTareaRecurrente> => {
    const body: Record<string, unknown> = {
      titulo: p.titulo,
      descripcion: p.descripcion ?? '',
      prioridad: p.prioridad ?? 'MEDIA',
      frecuencia: p.frecuencia,
      proxima_ejecucion: p.proxima_ejecucion,
      dias_semana: p.dias_semana ?? [],
      horas_dia: p.horas_dia ?? [],
    };
    if (p.dia_mes !== undefined && p.dia_mes !== null) body.dia_mes = p.dia_mes;
    if (p.proyecto) body.proyecto = p.proyecto;
    if (p.area) body.area = p.area;
    if (p.asignado_a) body.asignado_a = p.asignado_a;
    return post<PlantillaTareaRecurrente>(`${BASE}/recurrentes/`, body);
  },

  materializar: (fecha?: string): Promise<ResultadoMaterializacionRecurrente> =>
    post<ResultadoMaterializacionRecurrente>(
      `${BASE}/recurrentes/materializar/`,
      fecha ? { fecha } : {},
    ),

  remove: (id: string): Promise<void> => del<void>(`${BASE}/recurrentes/${id}/`),
};

export const minutasTareasService = {
  getAll: async (): Promise<MinutaReunion[]> =>
    toList<MinutaReunion>(await get<unknown>(`${BASE}/minutas/`)),

  create: (p: MinutaPayload): Promise<MinutaReunion> => {
    const body: Record<string, unknown> = {
      titulo: p.titulo,
      texto_fuente: p.texto_fuente ?? '',
      items_propuestos: p.items_propuestos,
    };
    if (p.fecha_reunion) body.fecha_reunion = p.fecha_reunion;
    return post<MinutaReunion>(`${BASE}/minutas/`, body);
  },

  confirmar: (
    id: string,
    opciones: { proyecto?: string | null; items_confirmados?: ItemBorradorMinuta[] } = {},
  ): Promise<{ minuta: MinutaReunion; tareas_creadas: Tarea[] }> => {
    const body: Record<string, unknown> = {};
    if (opciones.proyecto) body.proyecto = opciones.proyecto;
    if (opciones.items_confirmados) body.items_confirmados = opciones.items_confirmados;
    return post<{ minuta: MinutaReunion; tareas_creadas: Tarea[] }>(
      `${BASE}/minutas/${id}/confirmar/`,
      body,
    );
  },

  remove: (id: string): Promise<void> => del<void>(`${BASE}/minutas/${id}/`),
};

// ── Resumen Ejecutivo y Motor de Seguimiento ─────────────────────────────────

export const seguimientoTareasService = {
  getResumen: (fecha?: string): Promise<ResumenEjecutivoTareas> =>
    get<ResumenEjecutivoTareas>(`${BASE}/resumen/${armarQuery({ fecha })}`),

  getConfiguracion: (): Promise<ConfiguracionSeguimientoTareas> =>
    get<ConfiguracionSeguimientoTareas>(`${BASE}/configuracion/`),

  updateConfiguracion: (
    p: ConfiguracionSeguimientoPayload,
  ): Promise<ConfiguracionSeguimientoTareas> => {
    const body: Record<string, unknown> = {};
    if (p.zona_horaria !== undefined) body.zona_horaria = p.zona_horaria;
    if (p.hora_recordatorio_manana !== undefined)
      body.hora_recordatorio_manana = p.hora_recordatorio_manana;
    if (p.hora_recordatorio_tarde !== undefined)
      body.hora_recordatorio_tarde = p.hora_recordatorio_tarde;
    if (p.hora_reporte_gerencial !== undefined)
      body.hora_reporte_gerencial = p.hora_reporte_gerencial;
    if (p.horas_bloqueo_vencida !== undefined)
      body.horas_bloqueo_vencida = p.horas_bloqueo_vencida;
    if (p.gerente !== undefined) body.gerente = p.gerente;
    return patch<ConfiguracionSeguimientoTareas>(`${BASE}/configuracion/`, body);
  },

  ejecutarCiclo: (momento: MomentoSeguimiento = 'AUTO'): Promise<ResultadoSeguimientoTareas> =>
    post<ResultadoSeguimientoTareas>(`${BASE}/seguimiento/ejecutar/`, { momento }),
};
