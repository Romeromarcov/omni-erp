import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos ─────────────────────────────────────────────────────────────────────

/** Prioridad de un ticket de soporte (espejo de los choices del backend). */
export type PrioridadTicket = 'BAJA' | 'MEDIA' | 'ALTA' | 'URGENTE';

/**
 * Estados de un ticket de soporte (espejo de los choices del backend).
 * El backend no define una máquina de estados estricta para `cambiar_estado`
 * (acepta cualquier estado válido), pero la UI propone transiciones razonables
 * por estado vigente para guiar al agente. El backend re-valida.
 */
export type EstadoTicket =
  | 'ABIERTO'
  | 'ASIGNADO'
  | 'EN_PROGRESO'
  | 'PENDIENTE_CLIENTE'
  | 'RESUELTO'
  | 'CERRADO'
  | 'ESCALADO';

/** Tipo de interacción registrada en el timeline de un ticket. */
export type TipoInteraccion =
  | 'COMENTARIO'
  | 'EMAIL'
  | 'LLAMADA'
  | 'CAMBIO_ESTADO'
  | 'ASIGNACION'
  | 'ADJUNTO';

/** Visibilidad de un artículo de la base de conocimiento. */
export type VisibilidadArticulo = 'INTERNA' | 'PUBLICA';

/** Tipo de feedback del cliente. */
export type TipoFeedback = 'ENCUESTA_SATISFACCION' | 'SUGERENCIA' | 'QUEJA' | 'OTRO';

/**
 * Estados terminales: no se proponen más transiciones en la UI. CERRADO es el
 * único realmente final; RESUELTO permite reapertura/cierre. Se usa solo para
 * habilitar/inhabilitar botones (defensa en profundidad — el backend re-valida).
 */
export const ESTADOS_TICKET: readonly EstadoTicket[] = [
  'ABIERTO',
  'ASIGNADO',
  'EN_PROGRESO',
  'PENDIENTE_CLIENTE',
  'RESUELTO',
  'CERRADO',
  'ESCALADO',
] as const;

export const PRIORIDADES_TICKET: readonly PrioridadTicket[] = [
  'BAJA',
  'MEDIA',
  'ALTA',
  'URGENTE',
] as const;

/** True si el ticket está en un estado donde aún se opera (no cerrado). */
export function ticketEstaCerrado(estado: EstadoTicket): boolean {
  return estado === 'CERRADO';
}

// ── Categoría de ticket ───────────────────────────────────────────────────────

export interface CategoriaTicket {
  id_categoria_ticket: string;
  id_empresa: string;
  nombre_categoria: string;
  descripcion?: string | null;
  activo?: boolean;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface CategoriaTicketPayload {
  id_empresa: string;
  nombre_categoria: string;
  descripcion: string | null;
  activo: boolean;
}

export interface EstadisticasCategoria {
  total_tickets: number;
  tickets_abiertos: number;
  tickets_cerrados: number;
  porcentaje_resolucion: number;
}

// ── Ticket de soporte ───────────────────────────────────────────────────────

/**
 * Ticket de soporte. `estado_ticket`, `prioridad` y el agente cambian vía las
 * acciones (asignar_agente / cambiar_estado / escalar); el formulario de
 * alta/edición solo gestiona los datos descriptivos. Las fechas son read-only.
 */
export interface TicketSoporte {
  id_ticket: string;
  id_empresa: string;
  numero_ticket: string;
  asunto: string;
  descripcion: string;
  id_cliente_temp?: string | null;
  id_usuario_reporta_temp?: string | null;
  id_categoria_ticket: string;
  prioridad: PrioridadTicket;
  estado_ticket: EstadoTicket;
  id_agente_asignado_temp?: string | null;
  fecha_apertura?: string;
  fecha_ultima_actualizacion?: string;
  fecha_cierre?: string | null;
  sla_vencimiento?: string | null;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface TicketSoportePayload {
  id_empresa: string;
  numero_ticket: string;
  asunto: string;
  descripcion: string;
  id_categoria_ticket: string;
  prioridad: PrioridadTicket;
  estado_ticket: EstadoTicket;
  id_cliente_temp: string | null;
  id_agente_asignado_temp: string | null;
  sla_vencimiento: string | null;
}

export interface DashboardServicio {
  total_tickets: number;
  tickets_abiertos: number;
  tickets_cerrados_hoy: number;
  tiempo_promedio_resolucion_horas: number;
  tickets_por_prioridad: { prioridad: string; count: number }[];
  tickets_por_estado: { estado_ticket: string; count: number }[];
}

// ── Interacción ───────────────────────────────────────────────────────────────

export interface InteraccionTicket {
  id_interaccion: string;
  id_ticket: string;
  fecha_hora_interaccion?: string;
  tipo_interaccion: TipoInteraccion;
  id_usuario_interactor_temp?: string | null;
  contenido: string;
  fecha_creacion?: string;
}

/** Whitelist de campos editables al crear una interacción manual (CTF-005). */
export interface InteraccionTicketPayload {
  id_ticket: string;
  tipo_interaccion: TipoInteraccion;
  contenido: string;
}

// ── Base de conocimiento ──────────────────────────────────────────────────────

export interface BaseConocimientoArticulo {
  id_articulo: string;
  id_empresa: string;
  titulo: string;
  contenido: string;
  id_categoria_ticket?: string | null;
  palabras_clave?: string | null;
  fecha_publicacion?: string;
  fecha_ultima_revision?: string;
  activo?: boolean;
  visibilidad: VisibilidadArticulo;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface BaseConocimientoArticuloPayload {
  id_empresa: string;
  titulo: string;
  contenido: string;
  id_categoria_ticket: string | null;
  palabras_clave: string | null;
  visibilidad: VisibilidadArticulo;
  activo: boolean;
}

// ── Feedback del cliente ──────────────────────────────────────────────────────

export interface FeedbackCliente {
  id_feedback: string;
  id_empresa: string;
  id_cliente_temp?: string | null;
  id_ticket_origen?: string | null;
  fecha_feedback?: string;
  calificacion?: number | null;
  comentarios?: string | null;
  tipo_feedback: TipoFeedback;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface FeedbackClientePayload {
  id_empresa: string;
  tipo_feedback: TipoFeedback;
  calificacion: number | null;
  comentarios: string | null;
  id_cliente_temp: string | null;
  id_ticket_origen: string | null;
}

const BASE = '/servicio-cliente';

// ── Categorías de ticket (CRUD + activas + estadísticas) ──────────────────────

export const categoriasTicketService = {
  getAll: async (params?: { empresa?: string; search?: string }): Promise<CategoriaTicket[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('id_empresa', params.empresa);
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString();
    const response = await get<PaginatedResponse<CategoriaTicket> | CategoriaTicket[]>(
      `${BASE}/categorias-ticket/${query ? '?' + query : ''}`,
    );
    return toList<CategoriaTicket>(response);
  },

  getById: async (id: string): Promise<CategoriaTicket> =>
    get<CategoriaTicket>(`${BASE}/categorias-ticket/${id}/`),

  activas: async (): Promise<CategoriaTicket[]> => {
    const response = await get<PaginatedResponse<CategoriaTicket> | CategoriaTicket[]>(
      `${BASE}/categorias-ticket/activas/`,
    );
    return toList<CategoriaTicket>(response);
  },

  estadisticas: async (id: string): Promise<EstadisticasCategoria> =>
    get<EstadisticasCategoria>(`${BASE}/categorias-ticket/${id}/estadisticas/`),

  create: async (payload: CategoriaTicketPayload): Promise<CategoriaTicket> =>
    post<CategoriaTicket>(
      `${BASE}/categorias-ticket/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: CategoriaTicketPayload): Promise<CategoriaTicket> =>
    patch<CategoriaTicket>(
      `${BASE}/categorias-ticket/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/categorias-ticket/${id}/`);
  },
};

// ── Tickets de soporte (CRUD + workflow) ──────────────────────────────────────

export const ticketsSoporteService = {
  getAll: async (params?: {
    empresa?: string;
    estado?: string;
    prioridad?: string;
    categoria?: string;
    search?: string;
  }): Promise<TicketSoporte[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('id_empresa', params.empresa);
    if (params?.estado) qs.set('estado_ticket', params.estado);
    if (params?.prioridad) qs.set('prioridad', params.prioridad);
    if (params?.categoria) qs.set('id_categoria_ticket', params.categoria);
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString();
    const response = await get<PaginatedResponse<TicketSoporte> | TicketSoporte[]>(
      `${BASE}/tickets-soporte/${query ? '?' + query : ''}`,
    );
    return toList<TicketSoporte>(response);
  },

  getById: async (id: string): Promise<TicketSoporte> =>
    get<TicketSoporte>(`${BASE}/tickets-soporte/${id}/`),

  abiertos: async (agenteId?: string): Promise<TicketSoporte[]> => {
    const qs = agenteId ? `?agente_id=${encodeURIComponent(agenteId)}` : '';
    const response = await get<PaginatedResponse<TicketSoporte> | TicketSoporte[]>(
      `${BASE}/tickets-soporte/abiertos/${qs}`,
    );
    return toList<TicketSoporte>(response);
  },

  porPrioridad: async (prioridad: string): Promise<TicketSoporte[]> => {
    const response = await get<PaginatedResponse<TicketSoporte> | TicketSoporte[]>(
      `${BASE}/tickets-soporte/por_prioridad/?prioridad=${encodeURIComponent(prioridad)}`,
    );
    return toList<TicketSoporte>(response);
  },

  dashboard: async (agenteId?: string): Promise<DashboardServicio> => {
    const qs = agenteId ? `?agente_id=${encodeURIComponent(agenteId)}` : '';
    return get<DashboardServicio>(`${BASE}/tickets-soporte/dashboard/${qs}`);
  },

  create: async (payload: TicketSoportePayload): Promise<TicketSoporte> =>
    post<TicketSoporte>(`${BASE}/tickets-soporte/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: TicketSoportePayload): Promise<TicketSoporte> =>
    patch<TicketSoporte>(
      `${BASE}/tickets-soporte/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/tickets-soporte/${id}/`);
  },

  /** Asigna un agente y deja el ticket en ASIGNADO. */
  asignarAgente: async (id: string, agenteId: string): Promise<TicketSoporte> =>
    post<TicketSoporte>(`${BASE}/tickets-soporte/${id}/asignar_agente/`, { agente_id: agenteId }),

  /** Cambia el estado del ticket; comentario opcional para el timeline. */
  cambiarEstado: async (
    id: string,
    estado: EstadoTicket,
    comentario?: string,
  ): Promise<TicketSoporte> => {
    const body: Record<string, unknown> = { estado };
    if (comentario) body.comentario = comentario;
    return post<TicketSoporte>(`${BASE}/tickets-soporte/${id}/cambiar_estado/`, body);
  },

  /** Escala el ticket (estado ESCALADO + prioridad ALTA). */
  escalar: async (
    id: string,
    datos?: { razon?: string; nuevo_agente_id?: string | null },
  ): Promise<TicketSoporte> => {
    const body: Record<string, unknown> = {};
    if (datos?.razon) body.razon = datos.razon;
    if (datos?.nuevo_agente_id) body.nuevo_agente_id = datos.nuevo_agente_id;
    return post<TicketSoporte>(`${BASE}/tickets-soporte/${id}/escalar/`, body);
  },
};

// ── Interacciones del ticket (CRUD + agregar comentario) ──────────────────────

export const interaccionesTicketService = {
  getAll: async (params?: { ticket?: string; tipo?: string }): Promise<InteraccionTicket[]> => {
    const qs = new URLSearchParams();
    if (params?.ticket) qs.set('id_ticket', params.ticket);
    if (params?.tipo) qs.set('tipo_interaccion', params.tipo);
    const query = qs.toString();
    const response = await get<PaginatedResponse<InteraccionTicket> | InteraccionTicket[]>(
      `${BASE}/interacciones-ticket/${query ? '?' + query : ''}`,
    );
    const lista = toList<InteraccionTicket>(response);
    return params?.ticket ? lista.filter((i) => i.id_ticket === params.ticket) : lista;
  },

  getById: async (id: string): Promise<InteraccionTicket> =>
    get<InteraccionTicket>(`${BASE}/interacciones-ticket/${id}/`),

  create: async (payload: InteraccionTicketPayload): Promise<InteraccionTicket> =>
    post<InteraccionTicket>(
      `${BASE}/interacciones-ticket/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: InteraccionTicketPayload): Promise<InteraccionTicket> =>
    patch<InteraccionTicket>(
      `${BASE}/interacciones-ticket/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/interacciones-ticket/${id}/`);
  },

  /** Agrega un comentario (tipo COMENTARIO) a un ticket. */
  agregarComentario: async (ticketId: string, contenido: string): Promise<InteraccionTicket> =>
    post<InteraccionTicket>(`${BASE}/interacciones-ticket/agregar_comentario/`, {
      ticket_id: ticketId,
      contenido,
    }),
};

// ── Base de conocimiento (CRUD) ───────────────────────────────────────────────

export const articulosConocimientoService = {
  getAll: async (params?: {
    empresa?: string;
    visibilidad?: string;
    categoria?: string;
    search?: string;
  }): Promise<BaseConocimientoArticulo[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('id_empresa', params.empresa);
    if (params?.visibilidad) qs.set('visibilidad', params.visibilidad);
    if (params?.categoria) qs.set('id_categoria_ticket', params.categoria);
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString();
    const response = await get<PaginatedResponse<BaseConocimientoArticulo> | BaseConocimientoArticulo[]>(
      `${BASE}/articulos-conocimiento/${query ? '?' + query : ''}`,
    );
    return toList<BaseConocimientoArticulo>(response);
  },

  getById: async (id: string): Promise<BaseConocimientoArticulo> =>
    get<BaseConocimientoArticulo>(`${BASE}/articulos-conocimiento/${id}/`),

  create: async (payload: BaseConocimientoArticuloPayload): Promise<BaseConocimientoArticulo> =>
    post<BaseConocimientoArticulo>(
      `${BASE}/articulos-conocimiento/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (
    id: string,
    payload: BaseConocimientoArticuloPayload,
  ): Promise<BaseConocimientoArticulo> =>
    patch<BaseConocimientoArticulo>(
      `${BASE}/articulos-conocimiento/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/articulos-conocimiento/${id}/`);
  },
};

// ── Feedback del cliente (CRUD) ───────────────────────────────────────────────

export const feedbackClienteService = {
  getAll: async (params?: {
    empresa?: string;
    tipo?: string;
    ticket?: string;
  }): Promise<FeedbackCliente[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('id_empresa', params.empresa);
    if (params?.tipo) qs.set('tipo_feedback', params.tipo);
    if (params?.ticket) qs.set('id_ticket_origen', params.ticket);
    const query = qs.toString();
    const response = await get<PaginatedResponse<FeedbackCliente> | FeedbackCliente[]>(
      `${BASE}/feedback-cliente/${query ? '?' + query : ''}`,
    );
    return toList<FeedbackCliente>(response);
  },

  getById: async (id: string): Promise<FeedbackCliente> =>
    get<FeedbackCliente>(`${BASE}/feedback-cliente/${id}/`),

  create: async (payload: FeedbackClientePayload): Promise<FeedbackCliente> =>
    post<FeedbackCliente>(
      `${BASE}/feedback-cliente/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: FeedbackClientePayload): Promise<FeedbackCliente> =>
    patch<FeedbackCliente>(
      `${BASE}/feedback-cliente/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/feedback-cliente/${id}/`);
  },
};
