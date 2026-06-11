import { get } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

export interface Almacen {
  id_almacen: string;
  nombre_almacen: string;
  codigo_almacen?: string | null;
  id_empresa: string;
}

export const almacenesService = {
  /** Almacenes visibles del usuario (el backend ya filtra por empresas, R-CODE-1). */
  getAll: async (): Promise<Almacen[]> => {
    const response = await get<PaginatedResponse<Almacen> | Almacen[]>('/almacenes/almacenes/');
    return toList<Almacen>(response);
  },
};
