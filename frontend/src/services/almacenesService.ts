import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

export interface Almacen {
  id_almacen: string;
  nombre_almacen: string;
  codigo_almacen?: string | null;
  direccion?: string | null;
  activo?: boolean;
  id_empresa: string;
}

/**
 * Payload de escritura de Almacén: whitelist explícita de campos editables
 * (CTF-005, defensa en profundidad CWE-915).
 */
export interface AlmacenPayload {
  id_empresa: string;
  nombre_almacen: string;
  codigo_almacen: string;
  direccion: string | null;
}

export const almacenesService = {
  /** Almacenes visibles del usuario (el backend ya filtra por empresas, R-CODE-1). */
  getAll: async (): Promise<Almacen[]> => {
    const response = await get<PaginatedResponse<Almacen> | Almacen[]>('/almacenes/almacenes/');
    return toList<Almacen>(response);
  },

  create: async (payload: AlmacenPayload): Promise<Almacen> =>
    post<Almacen>('/almacenes/almacenes/', payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: AlmacenPayload): Promise<Almacen> =>
    patch<Almacen>(`/almacenes/almacenes/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`/almacenes/almacenes/${id}/`);
  },
};
