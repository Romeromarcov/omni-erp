/**
 * Servicio de Manufactura (1.I) — etapas de OF, costeo real y MRP básico.
 *
 * Endpoints del backend (PR #81, `apps/manufactura`):
 *   GET  /manufactura/ordenes-produccion/                — lista paginada de OF
 *   GET  /manufactura/ordenes-produccion/{id}/           — detalle de OF
 *   GET  /manufactura/ordenes-produccion/{id}/etapas/    — etapas en secuencia
 *   POST /manufactura/ordenes-produccion/{id}/avanzar-etapa/ — completa la siguiente etapa
 *   POST /manufactura/ordenes-produccion/{id}/completar/ — entrada de PT al costo real
 *   GET  /manufactura/ordenes-produccion/{id}/costeo/    — costeo real (mat + MO + OH)
 *   GET  /manufactura/ordenes-produccion/{id}/mrp/       — faltantes (BOM vs StockActual)
 *
 * Todos los montos viajan como STRING decimal (R-CODE-4) — nunca number.
 */
import { get, post } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Types ──────────────────────────────────────────────────────────────────

export type EstadoOrden = 'pendiente' | 'en_proceso' | 'finalizada' | 'cancelada' | 'parcial';

export interface OrdenProduccion {
  id: string;
  producto: string;
  /** Cantidad a producir, string decimal (R-CODE-4). */
  cantidad: string;
  fecha_inicio: string;
  fecha_fin: string | null;
  estado: EstadoOrden | string;
  lista_materiales: string | null;
  ruta_produccion: string | null;
  referencia_externa: string;
  observaciones: string;
}

export interface EtapaOrdenProduccion {
  id: string;
  orden_produccion: string;
  etapa: string;
  etapa_codigo: string;
  etapa_nombre: string;
  /** Posición en la secuencia (1 = primera). */
  orden: number;
  estado: 'pendiente' | 'completada';
  /** Montos como string decimal (R-CODE-4). */
  horas_trabajadas: string;
  tarifa_hora: string;
  cantidad_destajo: string;
  pago_destajo: string;
  costo_mano_obra: string;
  completada_por: number | null;
  fecha_completada: string | null;
  observaciones: string;
}

export interface AvanzarEtapaPayload {
  /** Strings decimales (R-CODE-4); el backend los parsea con Decimal. */
  horas_trabajadas?: string;
  tarifa_hora?: string;
  cantidad_destajo?: string;
  observaciones?: string;
}

export interface AvanzarEtapaResponse {
  estado_orden: string;
  etapa: EtapaOrdenProduccion;
  etapas_pendientes: number;
}

/** Desglose de costo real — todos los montos string decimal (R-CODE-4). */
export interface CostoProduccion {
  costo_materiales: string;
  mano_obra: string;
  costos_indirectos: string;
  costo_total: string;
  costo_unitario: string;
}

export interface CosteoOrdenResponse {
  orden_id: string;
  estado: string;
  costo: CostoProduccion;
  etapas: EtapaOrdenProduccion[];
}

export interface MrpFaltante {
  producto_id: string;
  producto: string;
  /** Cantidades como string decimal (R-CODE-4). */
  requerido: string;
  disponible: string;
  a_comprar: string;
}

export interface MrpResponse {
  orden_id: string;
  cantidad: string;
  faltantes: MrpFaltante[];
}

export interface CompletarOrdenPayload {
  almacen_id: string;
  /** String decimal; por defecto el backend usa la cantidad de la OF. */
  cantidad?: string;
}

export interface CompletarOrdenResponse {
  estado: string;
  produccion_id: string;
  costo: CostoProduccion;
}

export interface CrearOrdenPayload {
  /** UUID del producto terminado a fabricar. */
  producto: string;
  /** Cantidad a producir, string decimal (R-CODE-4). */
  cantidad: string;
  fecha_inicio: string;
  /** BOM/receta a explotar para el consumo de materiales (opcional). */
  lista_materiales?: string;
  referencia_externa?: string;
  observaciones?: string;
}

export interface ConsumirMaterialesPayload {
  almacen_id: string;
  incluir_opcionales?: boolean;
}

export interface ConsumoMaterial {
  id: string;
  orden_produccion: string;
  producto: string;
  /** Montos como string decimal (R-CODE-4). */
  cantidad: string;
  costo_unitario: string;
}

export interface ConsumirMaterialesResponse {
  estado: string;
  consumos: ConsumoMaterial[];
  costo_materiales: string;
}

export interface ListaMateriales {
  id: string;
  nombre: string;
  producto_final: string;
}

const BASE = '/manufactura/ordenes-produccion';
const BOM_BASE = '/manufactura/listas-materiales';

// ── Service ────────────────────────────────────────────────────────────────

export const manufacturaService = {
  /**
   * Crea una orden de producción en estado `pendiente`. El backend inyecta la
   * empresa (CTF-004) y materializa las etapas del catálogo de la empresa.
   */
  crearOrden: async (payload: CrearOrdenPayload): Promise<OrdenProduccion> => {
    return post<OrdenProduccion>(`${BASE}/`, payload as unknown as Record<string, unknown>);
  },

  /**
   * Explota la BOM de la orden y descuenta los materiales del inventario
   * (movimiento CONSUMO_PRODUCCION). El backend devuelve 400 si falta stock o
   * la orden no tiene lista de materiales.
   */
  consumirMateriales: async (
    ordenId: string,
    payload: ConsumirMaterialesPayload,
  ): Promise<ConsumirMaterialesResponse> => {
    return post<ConsumirMaterialesResponse>(
      `${BASE}/${ordenId}/consumir-materiales/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  /** Listas de materiales (BOM) de la empresa para asociarlas a una OF. */
  getListasMateriales: async (): Promise<ListaMateriales[]> => {
    const response = await get<ListaMateriales[] | PaginatedResponse<ListaMateriales>>(`${BOM_BASE}/`);
    return toList<ListaMateriales>(response);
  },

  /** Lista paginada de órdenes de producción (normaliza lista directa o DRF paginada). */
  getOrdenesPaginated: async (page = 1, pageSize = 20): Promise<PaginatedResponse<OrdenProduccion>> => {
    const response = await get<PaginatedResponse<OrdenProduccion> | OrdenProduccion[]>(
      `${BASE}/?page=${page}&page_size=${pageSize}`,
    );
    if (response && typeof response === 'object' && 'results' in response) {
      return response;
    }
    const arr = toList<OrdenProduccion>(response);
    return { count: arr.length, next: null, previous: null, results: arr };
  },

  getOrden: async (id: string): Promise<OrdenProduccion> => {
    return get<OrdenProduccion>(`${BASE}/${id}/`);
  },

  /** Etapas de la OF en secuencia con su estado y costo de mano de obra. */
  getEtapas: async (ordenId: string): Promise<EtapaOrdenProduccion[]> => {
    const response = await get<EtapaOrdenProduccion[] | PaginatedResponse<EtapaOrdenProduccion>>(
      `${BASE}/${ordenId}/etapas/`,
    );
    return toList<EtapaOrdenProduccion>(response);
  },

  /**
   * Completa la siguiente etapa pendiente (transición auditada: quién/cuándo,
   * horas × tarifa y destajo). El backend serializa los avances concurrentes
   * con select_for_update y devuelve 400 si no hay etapas pendientes.
   */
  avanzarEtapa: async (ordenId: string, payload: AvanzarEtapaPayload): Promise<AvanzarEtapaResponse> => {
    return post<AvanzarEtapaResponse>(
      `${BASE}/${ordenId}/avanzar-etapa/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  /** Costeo real acumulado: materiales (snapshot) + mano de obra + overhead. */
  getCosteo: async (ordenId: string): Promise<CosteoOrdenResponse> => {
    return get<CosteoOrdenResponse>(`${BASE}/${ordenId}/costeo/`);
  },

  /** MRP básico: explosión de BOM vs StockActual → faltantes a comprar. */
  getMrp: async (
    ordenId: string,
    opts: { almacenId?: string; incluirOpcionales?: boolean } = {},
  ): Promise<MrpResponse> => {
    const params = new URLSearchParams();
    if (opts.almacenId) params.set('almacen_id', opts.almacenId);
    if (opts.incluirOpcionales) params.set('incluir_opcionales', 'true');
    const qs = params.toString();
    return get<MrpResponse>(`${BASE}/${ordenId}/mrp/${qs ? `?${qs}` : ''}`);
  },

  /**
   * Cierra la OF registrando producción terminada valorada al costo real.
   * El backend responde 400 si quedan etapas pendientes.
   */
  completarOrden: async (ordenId: string, payload: CompletarOrdenPayload): Promise<CompletarOrdenResponse> => {
    return post<CompletarOrdenResponse>(
      `${BASE}/${ordenId}/completar/`,
      payload as unknown as Record<string, unknown>,
    );
  },
};
