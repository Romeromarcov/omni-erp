/**
 * Servicio de RRHH — empleados y cargos (workstream F: UI para el módulo hoy API-only).
 *
 * Endpoints del backend (`apps/rrhh`, base /api/rrhh/):
 *   GET   /rrhh/empleados/        — lista paginada (R-CODE-1: solo empresas visibles)
 *   GET   /rrhh/empleados/{id}/   — detalle
 *   POST  /rrhh/empleados/        — crea empleado (requiere `empresa` visible, SEC-M1)
 *   PATCH /rrhh/empleados/{id}/   — edición parcial
 *   GET   /rrhh/cargos/           — catálogo de cargos (propios + globales empresa=null)
 *
 * El salario mensual vive en `documento_json.salario_mensual` como STRING decimal
 * (R-CODE-4): es el puente documentado que lee `apps/nomina/services._salario_mensual`
 * mientras `rrhh.Empleado` no tiene campo de salario propio.
 */
import { get, patch, post } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Types ──────────────────────────────────────────────────────────────────

export interface Cargo {
  id: number;
  empresa: string | null;
  nombre: string;
  descripcion: string | null;
  activo: boolean;
}

/** Claves conocidas del documento_json del empleado (extensible). */
export interface DocumentoEmpleado {
  /** Salario mensual como string decimal (R-CODE-4); lo lee el motor de nómina. */
  salario_mensual?: string;
  [key: string]: unknown;
}

export interface Empleado {
  /** PK entera del modelo rrhh.Empleado (las claves del body de procesar usan String(id)). */
  id: number;
  empresa: string;
  referencia_externa: string | null;
  documento_json: DocumentoEmpleado | null;
  nombre: string;
  apellido: string;
  cedula: string;
  cargo: number | null;
  fecha_ingreso: string;
  activo: boolean;
  contacto: string | null;
}

export interface EmpleadoPayload {
  empresa: string;
  nombre: string;
  apellido: string;
  cedula: string;
  cargo: number | null;
  fecha_ingreso: string;
  activo: boolean;
  documento_json: DocumentoEmpleado | null;
}

const BASE = '/rrhh';

/** Máximo de páginas a recorrer en catálogos (el backend pagina fijo a 20). */
const MAX_PAGINAS = 100;

/**
 * Recorre la lista paginada acumulando todos los elementos (el backend usa
 * PageNumberPagination sin `page_size` configurable, así que `?page_size=` no
 * tiene efecto y hay que caminar las páginas).
 */
async function fetchTodas<T>(endpoint: string): Promise<T[]> {
  const sep = endpoint.includes('?') ? '&' : '?';
  const acumulado: T[] = [];
  for (let page = 1; page <= MAX_PAGINAS; page++) {
    const respuesta = await get<PaginatedResponse<T> | T[]>(`${endpoint}${sep}page=${page}`);
    acumulado.push(...toList<T>(respuesta));
    const next = Array.isArray(respuesta) ? null : (respuesta.next ?? null);
    if (!next) break;
  }
  return acumulado;
}

// ── Service ────────────────────────────────────────────────────────────────

export const rrhhService = {
  /** Lista paginada de empleados (normaliza lista directa o DRF paginada). */
  getEmpleadosPaginated: async (page = 1): Promise<PaginatedResponse<Empleado>> => {
    const response = await get<PaginatedResponse<Empleado> | Empleado[]>(
      `${BASE}/empleados/?page=${page}`,
    );
    if (response && typeof response === 'object' && 'results' in response) {
      return response;
    }
    const arr = toList<Empleado>(response);
    return { count: arr.length, next: null, previous: null, results: arr };
  },

  getEmpleado: async (id: number | string): Promise<Empleado> => {
    return get<Empleado>(`${BASE}/empleados/${id}/`);
  },

  /**
   * Todos los empleados de UNA empresa (activos e inactivos), caminando las
   * páginas. El backend no filtra por empresa en querystring, se filtra aquí;
   * los inactivos se necesitan para nombrar recibos históricos de nómina.
   */
  getEmpleadosDeEmpresa: async (empresaId: string): Promise<Empleado[]> => {
    const todos = await fetchTodas<Empleado>(`${BASE}/empleados/`);
    return todos.filter((e) => e.empresa === empresaId);
  },

  /** Crea el empleado; `empresa` debe ser una empresa visible (SEC-M1). */
  crearEmpleado: async (payload: EmpleadoPayload): Promise<Empleado> => {
    return post<Empleado>(`${BASE}/empleados/`, payload as unknown as Record<string, unknown>);
  },

  /** Edición parcial (PATCH): no reenvía `empresa` para no mover de tenant. */
  actualizarEmpleado: async (
    id: number | string,
    payload: Partial<EmpleadoPayload>,
  ): Promise<Empleado> => {
    return patch<Empleado>(
      `${BASE}/empleados/${id}/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  /** Catálogo de cargos visibles (incluye los globales con empresa=null). */
  getCargos: async (): Promise<Cargo[]> => {
    return fetchTodas<Cargo>(`${BASE}/cargos/`);
  },
};
