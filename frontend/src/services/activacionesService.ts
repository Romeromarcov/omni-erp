/**
 * Servicio del módulo de Activaciones (eventos en puntos de venta).
 *
 * Cablea `/api/activaciones/`: calendarios, recursos con capacidad simultánea
 * (promotoras, igloos…) y eventos. El aislamiento multi-tenant lo aplica el
 * backend; el front no envía `id_empresa`. Cada payload se arma con whitelist
 * explícita de campos (CTF-005, CWE-915).
 */
import { get, post, patch, del } from './api';
import { toList } from '../utils/api';

// ── Tipos (espejo de los serializers del backend) ─────────────────────────────

export type EstadoEvento = 'PROGRAMADO' | 'REALIZADO' | 'CANCELADO';

export const ESTADOS_EVENTO: readonly EstadoEvento[] = [
  'PROGRAMADO',
  'REALIZADO',
  'CANCELADO',
] as const;

export interface Calendario {
  id_calendario: string;
  id_empresa: string;
  nombre: string;
  google_calendar_id: string;
  zona_horaria: string;
  es_predeterminado: boolean;
  activo: boolean;
}

export interface Recurso {
  id_recurso: string;
  id_empresa: string;
  calendario: string;
  codigo: string;
  nombre: string;
  capacidad: number;
  activo: boolean;
}

export interface UsoRecurso {
  recurso: string;
  recurso_codigo: string;
  cantidad: number;
}

export interface EventoActivacion {
  id_evento: string;
  id_empresa: string;
  calendario: string;
  cliente: string | null;
  cliente_nombre: string;
  vendedor: string | null;
  vendedor_nombre: string;
  ubicacion: string;
  inicio: string;
  fin: string;
  materiales: string[];
  notas: string;
  estado: EstadoEvento;
  origen: 'WEB' | 'BOT';
  google_event_id: string;
  sync_error: string;
  usos: UsoRecurso[];
}

export interface DisponibilidadRecurso {
  codigo: string;
  nombre: string;
  capacidad: number;
  usado: number;
  libres: number;
}

// ── Payloads ──────────────────────────────────────────────────────────────────

export interface CalendarioPayload {
  nombre: string;
  google_calendar_id: string;
  zona_horaria: string;
  es_predeterminado: boolean;
}

export interface RecursoPayload {
  calendario: string;
  codigo: string;
  nombre: string;
  capacidad: number;
}

export interface EventoPayload {
  calendario?: string;
  cliente_nombre: string;
  vendedor_nombre?: string;
  ubicacion: string;
  /** ISO 8601 con zona (p. ej. el resultado de `Date#toISOString`). */
  inicio: string;
  fin: string;
  materiales?: string[];
  notas?: string;
  /** {codigo_recurso: cantidad}. */
  usos: Record<string, number>;
}

export interface FiltroEventos {
  estado?: EstadoEvento | '';
  desde?: string;
  hasta?: string;
}

const BASE = '/activaciones';

function query(params: Record<string, string | undefined>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) qs.set(k, v);
  const s = qs.toString();
  return s ? `?${s}` : '';
}

// ── Calendarios ───────────────────────────────────────────────────────────────

export const calendariosService = {
  getAll: async (): Promise<Calendario[]> =>
    toList<Calendario>(await get<unknown>(`${BASE}/calendarios/`)),

  create: (p: CalendarioPayload): Promise<Calendario> =>
    post<Calendario>(`${BASE}/calendarios/`, {
      nombre: p.nombre,
      google_calendar_id: p.google_calendar_id,
      zona_horaria: p.zona_horaria,
      es_predeterminado: p.es_predeterminado,
    }),

  update: (id: string, p: Partial<CalendarioPayload>): Promise<Calendario> => {
    const body: Record<string, unknown> = {};
    if (p.nombre !== undefined) body.nombre = p.nombre;
    if (p.google_calendar_id !== undefined) body.google_calendar_id = p.google_calendar_id;
    if (p.zona_horaria !== undefined) body.zona_horaria = p.zona_horaria;
    if (p.es_predeterminado !== undefined) body.es_predeterminado = p.es_predeterminado;
    return patch<Calendario>(`${BASE}/calendarios/${id}/`, body);
  },

  remove: (id: string): Promise<void> => del<void>(`${BASE}/calendarios/${id}/`),

  /** Capacidad y recursos libres (pico simultáneo) en [inicio, fin). */
  disponibilidad: async (
    id: string,
    inicio: string,
    fin: string,
  ): Promise<DisponibilidadRecurso[]> =>
    get<DisponibilidadRecurso[]>(
      `${BASE}/calendarios/${id}/disponibilidad/${query({ inicio, fin })}`,
    ),
};

// ── Recursos ──────────────────────────────────────────────────────────────────

export const recursosService = {
  getAll: async (): Promise<Recurso[]> =>
    toList<Recurso>(await get<unknown>(`${BASE}/recursos/`)),

  create: (p: RecursoPayload): Promise<Recurso> =>
    post<Recurso>(`${BASE}/recursos/`, {
      calendario: p.calendario,
      codigo: p.codigo,
      nombre: p.nombre,
      capacidad: p.capacidad,
    }),

  update: (id: string, p: { nombre?: string; capacidad?: number }): Promise<Recurso> => {
    const body: Record<string, unknown> = {};
    if (p.nombre !== undefined) body.nombre = p.nombre;
    if (p.capacidad !== undefined) body.capacidad = p.capacidad;
    return patch<Recurso>(`${BASE}/recursos/${id}/`, body);
  },

  remove: (id: string): Promise<void> => del<void>(`${BASE}/recursos/${id}/`),
};

// ── Eventos ───────────────────────────────────────────────────────────────────

export const eventosService = {
  getAll: async (f: FiltroEventos = {}): Promise<EventoActivacion[]> =>
    toList<EventoActivacion>(
      await get<unknown>(
        `${BASE}/eventos/${query({ estado: f.estado || undefined, desde: f.desde, hasta: f.hasta })}`,
      ),
    ),

  /** Crea un evento. Si no cabe por capacidad el backend responde 409 con `{error, detalle}`. */
  create: (p: EventoPayload): Promise<EventoActivacion> => {
    const body: Record<string, unknown> = {
      cliente_nombre: p.cliente_nombre,
      ubicacion: p.ubicacion,
      inicio: p.inicio,
      fin: p.fin,
      usos: p.usos,
      materiales: p.materiales ?? [],
      notas: p.notas ?? '',
    };
    if (p.calendario) body.calendario = p.calendario;
    if (p.vendedor_nombre) body.vendedor_nombre = p.vendedor_nombre;
    return post<EventoActivacion>(`${BASE}/eventos/`, body);
  },

  cancelar: (id: string): Promise<EventoActivacion> =>
    post<EventoActivacion>(`${BASE}/eventos/${id}/cancelar/`, {}),
};
