import { get, patch, post } from './api';
import { toList, type PaginatedResponse } from '../utils/api';
import type { components } from '../api/schema';

export type CrmEtapa = components['schemas']['Etapa'];
export type CrmPipeline = components['schemas']['Pipeline'];
export type CrmLead = components['schemas']['Lead'];
export type CrmActividad = components['schemas']['Actividad'];
export type TipoEtapa = NonNullable<CrmEtapa['tipo']>;
export type FuenteLead = NonNullable<CrmLead['fuente']>;
export type TipoActividad = NonNullable<CrmActividad['tipo']>;

export interface CreatePipelinePayload {
  id_empresa?: string;
  nombre: string;
  es_predeterminado?: boolean;
}

export interface CreateEtapaPayload {
  id_empresa?: string;
  pipeline: string;
  nombre: string;
  orden?: number;
  tipo?: TipoEtapa;
}

export interface CreateLeadPayload {
  id_empresa?: string;
  nombre: string;
  apellido?: string;
  empresa_nombre?: string;
  email?: string;
  telefono?: string;
  mensaje?: string;
  fuente?: FuenteLead;
  pipeline?: string;
  etapa?: string;
  propietario?: string;
}

export interface CreateActividadPayload {
  id_empresa?: string;
  lead: string;
  tipo?: TipoActividad;
  asunto: string;
  descripcion?: string;
  fecha_vencimiento?: string | null;
  completada?: boolean;
  asignado_a?: string | null;
  tarea?: string | null;
}

export interface LeadsKanbanPageResult {
  items: CrmLead[];
  total: number;
  truncado: boolean;
}

const MAX_PAGINAS_KANBAN = 25;

function buildQuery(entries: Array<[string, string | boolean | undefined | null]>): string {
  const qs = new URLSearchParams();
  for (const [key, val] of entries) {
    if (val === undefined || val === null || val === '') continue;
    qs.set(key, String(val));
  }
  const encoded = qs.toString();
  return encoded ? `?${encoded}` : '';
}

async function fetchTodasPaginas<T>(
  endpoint: string,
  maxPaginas = MAX_PAGINAS_KANBAN,
): Promise<{ items: T[]; total: number; truncado: boolean }> {
  const sep = endpoint.includes('?') ? '&' : '?';
  const acumulado: T[] = [];
  let total: number | null = null;

  for (let page = 1; page <= maxPaginas; page++) {
    const url = page === 1 ? endpoint : `${endpoint}${sep}page=${page}`;
    const raw = await get<PaginatedResponse<T> | T[]>(url);
    acumulado.push(...toList<T>(raw));
    if (!Array.isArray(raw) && typeof raw.count === 'number') {
      total = raw.count;
    }
    const next = Array.isArray(raw) ? null : (raw.next ?? null);
    if (!next) {
      return { items: acumulado, total: total ?? acumulado.length, truncado: false };
    }
  }

  return { items: acumulado, total: total ?? acumulado.length, truncado: true };
}

export const crmCrmService = {
  getPipelines: async (empresaId?: string | null): Promise<CrmPipeline[]> => {
    const query = buildQuery([['empresa', empresaId]]);
    const { items } = await fetchTodasPaginas<CrmPipeline>(`/crm/pipelines/${query}`);
    return items;
  },

  asegurarPipelinePredeterminado: async (empresaId?: string | null): Promise<CrmPipeline> => {
    const payload = empresaId ? { id_empresa: empresaId } : {};
    return post<CrmPipeline>('/crm/pipelines/asegurar-predeterminado/', payload);
  },

  createPipeline: async (payload: CreatePipelinePayload): Promise<CrmPipeline> =>
    post<CrmPipeline>('/crm/pipelines/', payload as unknown as Record<string, unknown>),

  reordenarEtapas: async (pipelineId: string, etapas: string[]): Promise<CrmPipeline> =>
    post<CrmPipeline>(`/crm/pipelines/${pipelineId}/reordenar-etapas/`, { etapas }),

  getEtapas: async (params?: { empresa?: string | null; pipeline?: string | null }): Promise<CrmEtapa[]> => {
    const query = buildQuery([
      ['empresa', params?.empresa],
      ['pipeline', params?.pipeline],
    ]);
    const { items } = await fetchTodasPaginas<CrmEtapa>(`/crm/etapas/${query}`);
    return items;
  },

  createEtapa: async (payload: CreateEtapaPayload): Promise<CrmEtapa> =>
    post<CrmEtapa>('/crm/etapas/', payload as unknown as Record<string, unknown>),

  getLeadsKanban: async (
    params?: {
      empresa?: string | null;
      pipeline?: string | null;
      etapa?: string | null;
      fuente?: string | null;
      search?: string | null;
    },
    maxPaginas = MAX_PAGINAS_KANBAN,
  ): Promise<LeadsKanbanPageResult> => {
    const query = buildQuery([
      ['empresa', params?.empresa],
      ['pipeline', params?.pipeline],
      ['etapa', params?.etapa],
      ['fuente', params?.fuente],
      ['search', params?.search],
    ]);
    return fetchTodasPaginas<CrmLead>(`/crm/leads/${query}`, maxPaginas);
  },

  getLeads: async (params?: {
    empresa?: string | null;
    pipeline?: string | null;
    etapa?: string | null;
    fuente?: string | null;
    search?: string | null;
  }): Promise<CrmLead[]> => {
    const { items } = await crmCrmService.getLeadsKanban(params);
    return items;
  },

  createLead: async (payload: CreateLeadPayload): Promise<CrmLead> =>
    post<CrmLead>('/crm/leads/', payload as unknown as Record<string, unknown>),

  updateLead: async (leadId: string, payload: Partial<CreateLeadPayload>): Promise<CrmLead> =>
    patch<CrmLead>(`/crm/leads/${leadId}/`, payload as unknown as Record<string, unknown>),

  moverEtapaLead: async (leadId: string, etapaId: string): Promise<CrmLead> =>
    post<CrmLead>(`/crm/leads/${leadId}/mover-etapa/`, { etapa: etapaId }),

  getActividades: async (params?: {
    empresa?: string | null;
    lead?: string | null;
    completada?: boolean | null;
    tipo?: string | null;
  }): Promise<CrmActividad[]> => {
    const query = buildQuery([
      ['empresa', params?.empresa],
      ['lead', params?.lead],
      ['completada', params?.completada ?? undefined],
      ['tipo', params?.tipo],
    ]);
    const { items } = await fetchTodasPaginas<CrmActividad>(`/crm/actividades/${query}`);
    return items;
  },

  createActividad: async (payload: CreateActividadPayload): Promise<CrmActividad> =>
    post<CrmActividad>('/crm/actividades/', payload as unknown as Record<string, unknown>),

  completarActividad: async (
    actividadId: string,
    completada = true,
    descripcion?: string,
  ): Promise<CrmActividad> => {
    const payload: Record<string, unknown> = { completada };
    if (descripcion !== undefined) {
      payload.descripcion = descripcion;
    }
    return post<CrmActividad>(`/crm/actividades/${actividadId}/completar/`, payload);
  },
};
