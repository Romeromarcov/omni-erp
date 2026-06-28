/**
 * Servicio de Datos Maestros de Manufactura (1.I) — CRUD de los catálogos que
 * alimentan la Orden de Producción: Listas de Materiales (BOM) + componentes,
 * Rutas de Producción + pasos (operaciones), Operaciones y Centros de Trabajo.
 *
 * Backend `apps/manufactura` (prefijo /api/manufactura/):
 *   listas-materiales/            + listas-materiales-detalle/   (BOM + componentes)
 *   rutas-produccion/             + rutas-produccion-detalle/    (ruta + pasos)
 *   centros-trabajo/                                             (centros de trabajo)
 *   operaciones-produccion/                                      (operaciones de los pasos)
 *
 * `empresa`/`id_empresa` se inyecta en el backend (CTF-004) — no se envía.
 * Todos los montos viajan como STRING decimal (R-CODE-4) — nunca number.
 */
import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Listas de Materiales (BOM) — cabecera ────────────────────────────────────

/** Cabecera de un BOM: el producto final que se fabrica y su versión/referencia. */
export interface ListaMateriales {
  id: string;
  empresa?: string;
  producto_final: string;
  nombre: string;
  descripcion: string;
  referencia_externa: string;
}

/** Payload de escritura de ListaMateriales (whitelist; empresa la inyecta el backend). */
export interface ListaMaterialesPayload {
  producto_final: string;
  nombre: string;
  descripcion: string;
  referencia_externa: string;
}

/** Componente de un BOM: producto requerido y su cantidad por unidad fabricada. */
export interface ListaMaterialesDetalle {
  id_detalle_lista: string;
  id_lista_materiales: string;
  id_producto: string;
  cantidad_requerida: string;
  id_unidad_medida: string;
  es_opcional: boolean;
  observaciones: string;
}

/** Payload de escritura de un componente del BOM (cantidad como string, R-CODE-4). */
export interface ListaMaterialesDetallePayload {
  id_lista_materiales: string;
  id_producto: string;
  cantidad_requerida: string;
  id_unidad_medida: string;
  es_opcional: boolean;
  observaciones: string;
}

// ── Centros de Trabajo ───────────────────────────────────────────────────────

export type TipoCentro = 'MAQUINA' | 'MANUAL' | 'ENSAMBLE' | 'CONTROL_CALIDAD' | 'EMPAQUE';

/** Centro de trabajo: dónde se ejecutan las operaciones (capacidad + costo/hora). */
export interface CentroTrabajo {
  id_centro_trabajo: string;
  id_empresa?: string;
  codigo_centro: string;
  nombre_centro: string;
  descripcion: string;
  tipo_centro: TipoCentro | string;
  capacidad_horas_dia: string;
  costo_hora: string;
  activo: boolean;
  fecha_creacion?: string;
}

/**
 * Payload de escritura de CentroTrabajo (montos string). El ViewSet de
 * manufactura NO usa `EmpresaInjectMixin`: el cliente debe enviar `id_empresa`.
 */
export interface CentroTrabajoPayload {
  id_empresa: string;
  codigo_centro: string;
  nombre_centro: string;
  descripcion: string;
  tipo_centro: string;
  capacidad_horas_dia: string;
  costo_hora: string;
  activo: boolean;
}

// ── Operaciones de Producción (las usa cada paso de la ruta) ──────────────────

export interface OperacionProduccion {
  id_operacion: string;
  id_empresa?: string;
  codigo_operacion: string;
  nombre_operacion: string;
  descripcion: string;
  tiempo_estandar_minutos: string;
  activo: boolean;
  fecha_creacion?: string;
}

export interface OperacionProduccionPayload {
  codigo_operacion: string;
  nombre_operacion: string;
  descripcion: string;
  tiempo_estandar_minutos: string;
  activo: boolean;
}

// ── Rutas de Producción — cabecera ───────────────────────────────────────────

/** Cabecera de una ruta/proceso de fabricación. */
export interface RutaProduccion {
  id: string;
  empresa?: string;
  nombre: string;
  descripcion: string;
  referencia_externa: string;
}

export interface RutaProduccionPayload {
  nombre: string;
  descripcion: string;
  referencia_externa: string;
}

/** Paso de una ruta: secuencia, operación, centro de trabajo y tiempos (minutos). */
export interface RutaProduccionDetalle {
  id_detalle_ruta: string;
  id_ruta_produccion: string;
  id_operacion: string;
  id_centro_trabajo: string;
  numero_secuencia: number;
  tiempo_preparacion_minutos: string;
  tiempo_operacion_minutos: string;
  observaciones: string;
}

export interface RutaProduccionDetallePayload {
  id_ruta_produccion: string;
  id_operacion: string;
  id_centro_trabajo: string;
  numero_secuencia: number;
  tiempo_preparacion_minutos: string;
  tiempo_operacion_minutos: string;
  observaciones: string;
}

// ── Endpoints ────────────────────────────────────────────────────────────────

const BOM = '/manufactura/listas-materiales';
const BOM_DET = '/manufactura/listas-materiales-detalle';
const RUTA = '/manufactura/rutas-produccion';
const RUTA_DET = '/manufactura/rutas-produccion-detalle';
const CENTRO = '/manufactura/centros-trabajo';
const OPERACION = '/manufactura/operaciones-produccion';

// ── Listas de Materiales (BOM) ───────────────────────────────────────────────

export const listasMaterialesService = {
  getAll: async (): Promise<ListaMateriales[]> => {
    const r = await get<PaginatedResponse<ListaMateriales> | ListaMateriales[]>(`${BOM}/`);
    return toList<ListaMateriales>(r);
  },

  getById: async (id: string): Promise<ListaMateriales> => get<ListaMateriales>(`${BOM}/${id}/`),

  create: async (payload: ListaMaterialesPayload): Promise<ListaMateriales> =>
    post<ListaMateriales>(`${BOM}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: ListaMaterialesPayload): Promise<ListaMateriales> =>
    patch<ListaMateriales>(`${BOM}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BOM}/${id}/`);
  },
};

export const listasMaterialesDetalleService = {
  getAll: async (params?: { lista?: string }): Promise<ListaMaterialesDetalle[]> => {
    const r = await get<PaginatedResponse<ListaMaterialesDetalle> | ListaMaterialesDetalle[]>(`${BOM_DET}/`);
    const lista = toList<ListaMaterialesDetalle>(r);
    // El backend filtra por empresa; reforzamos por BOM en el cliente para que
    // cada cabecera muestre solo sus propios componentes.
    return params?.lista ? lista.filter((d) => d.id_lista_materiales === params.lista) : lista;
  },

  create: async (payload: ListaMaterialesDetallePayload): Promise<ListaMaterialesDetalle> =>
    post<ListaMaterialesDetalle>(`${BOM_DET}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: ListaMaterialesDetallePayload): Promise<ListaMaterialesDetalle> =>
    patch<ListaMaterialesDetalle>(`${BOM_DET}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BOM_DET}/${id}/`);
  },
};

// ── Rutas de Producción ──────────────────────────────────────────────────────

export const rutasProduccionService = {
  getAll: async (): Promise<RutaProduccion[]> => {
    const r = await get<PaginatedResponse<RutaProduccion> | RutaProduccion[]>(`${RUTA}/`);
    return toList<RutaProduccion>(r);
  },

  getById: async (id: string): Promise<RutaProduccion> => get<RutaProduccion>(`${RUTA}/${id}/`),

  create: async (payload: RutaProduccionPayload): Promise<RutaProduccion> =>
    post<RutaProduccion>(`${RUTA}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: RutaProduccionPayload): Promise<RutaProduccion> =>
    patch<RutaProduccion>(`${RUTA}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${RUTA}/${id}/`);
  },
};

export const rutasProduccionDetalleService = {
  getAll: async (params?: { ruta?: string }): Promise<RutaProduccionDetalle[]> => {
    const r = await get<PaginatedResponse<RutaProduccionDetalle> | RutaProduccionDetalle[]>(`${RUTA_DET}/`);
    const lista = toList<RutaProduccionDetalle>(r);
    return params?.ruta ? lista.filter((d) => d.id_ruta_produccion === params.ruta) : lista;
  },

  create: async (payload: RutaProduccionDetallePayload): Promise<RutaProduccionDetalle> =>
    post<RutaProduccionDetalle>(`${RUTA_DET}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: RutaProduccionDetallePayload): Promise<RutaProduccionDetalle> =>
    patch<RutaProduccionDetalle>(`${RUTA_DET}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${RUTA_DET}/${id}/`);
  },
};

// ── Centros de Trabajo ───────────────────────────────────────────────────────

export const centrosTrabajoService = {
  getAll: async (): Promise<CentroTrabajo[]> => {
    const r = await get<PaginatedResponse<CentroTrabajo> | CentroTrabajo[]>(`${CENTRO}/`);
    return toList<CentroTrabajo>(r);
  },

  getById: async (id: string): Promise<CentroTrabajo> => get<CentroTrabajo>(`${CENTRO}/${id}/`),

  create: async (payload: CentroTrabajoPayload): Promise<CentroTrabajo> =>
    post<CentroTrabajo>(`${CENTRO}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: CentroTrabajoPayload): Promise<CentroTrabajo> =>
    patch<CentroTrabajo>(`${CENTRO}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${CENTRO}/${id}/`);
  },
};

// ── Operaciones de Producción (catálogo de los pasos de la ruta) ─────────────

export const operacionesProduccionService = {
  getAll: async (): Promise<OperacionProduccion[]> => {
    const r = await get<PaginatedResponse<OperacionProduccion> | OperacionProduccion[]>(`${OPERACION}/`);
    return toList<OperacionProduccion>(r);
  },

  create: async (payload: OperacionProduccionPayload): Promise<OperacionProduccion> =>
    post<OperacionProduccion>(`${OPERACION}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: OperacionProduccionPayload): Promise<OperacionProduccion> =>
    patch<OperacionProduccion>(`${OPERACION}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${OPERACION}/${id}/`);
  },
};
