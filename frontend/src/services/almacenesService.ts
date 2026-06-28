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
  /** Almacenes visibles del usuario (el backend ya filtra por empresas, R-CODE-1).
   * Recorre todas las páginas: los selectores de almacén necesitan el catálogo
   * completo, no sólo los 20 primeros. */
  getAll: async (): Promise<Almacen[]> => {
    const acumulado: Almacen[] = [];
    for (let page = 1; page <= 50; page++) {
      const response = await get<PaginatedResponse<Almacen> | Almacen[]>(
        `/almacenes/almacenes/?page=${page}`,
      );
      acumulado.push(...toList<Almacen>(response));
      const next = Array.isArray(response) ? null : (response.next ?? null);
      if (!next) break;
    }
    return acumulado;
  },

  create: async (payload: AlmacenPayload): Promise<Almacen> =>
    post<Almacen>('/almacenes/almacenes/', payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: AlmacenPayload): Promise<Almacen> =>
    patch<Almacen>(`/almacenes/almacenes/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`/almacenes/almacenes/${id}/`);
  },
};
