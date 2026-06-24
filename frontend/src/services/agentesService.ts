/**
 * Servicio del módulo de Agentes IA (M9).
 *
 * Cablea el CRUD de predicciones (`/api/agentes/predicciones/`) y sus acciones
 * custom (sugerencias activas, responder/evaluar, disparar análisis y métricas
 * del clasificador de gastos). El aislamiento multi-tenant lo aplica el backend
 * (filtra por las empresas visibles del usuario); el front no envía id_empresa.
 *
 * Cada payload se construye con whitelist explícita de campos (CTF-005,
 * defensa CWE-915): nunca se reenvía el objeto del backend tal cual.
 */
import { get, post, patch } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Choices (espejo de AGENTE_CHOICES / RESULTADO_CHOICES del backend) ─────────

/** Identificadores de agente (espejo de PrediccionAgente.AGENTE_CHOICES). */
export type Agente =
  | 'clasificador_gastos'
  | 'cobranza_estratega'
  | 'reorden_sugeridor'
  | 'personalizacion_capa2';

/** Resultado de la revisión humana (espejo de PrediccionAgente.RESULTADO_CHOICES). */
export type ResultadoHumano = 'pendiente' | 'aceptada' | 'rechazada';

export const AGENTES: readonly Agente[] = [
  'clasificador_gastos',
  'cobranza_estratega',
  'reorden_sugeridor',
  'personalizacion_capa2',
] as const;

export const RESULTADOS_HUMANOS: readonly ResultadoHumano[] = [
  'pendiente',
  'aceptada',
  'rechazada',
] as const;

// ── Tipos ──────────────────────────────────────────────────────────────────────

/** Predicción emitida por un agente (espejo del PrediccionAgenteSerializer). */
export interface PrediccionAgente {
  id_prediccion: string;
  esta_vigente: boolean;
  agente: Agente | string;
  input_texto: string;
  input_monto: string | null;
  input_metadata: Record<string, unknown>;
  categoria_predicha: string;
  confianza: number;
  razonamiento: string;
  alternativas: unknown[];
  resultado_humano: ResultadoHumano | string;
  categoria_correcta: string;
  modelo_llm: string;
  latencia_ms: number;
  fecha_prediccion: string;
  id_empresa: string;
}

/** Tarjeta de sugerencia activa (forma plana de sugerencias-activas). */
export interface SugerenciaActiva {
  id: string;
  agente: Agente | string;
  titulo: string;
  descripcion: string;
  categoria: string;
  confianza: number;
  monto: string | null;
  metadata: Record<string, unknown>;
  url_accion: string;
  fecha: string;
}

export interface SugerenciasActivasResponse {
  sugerencias: SugerenciaActiva[];
  total: number;
}

/** Payload de POST predicciones/{id}/responder/. */
export interface ResponderPayload {
  accion: 'aceptar' | 'rechazar';
  comentario?: string;
}

export interface RespuestaPrediccion {
  id: string;
  resultado_humano: ResultadoHumano | string;
  agente: Agente | string;
  categoria: string;
}

/** Payload de PATCH predicciones/{id}/evaluar/. */
export interface EvaluarPayload {
  resultado_humano: 'aceptada' | 'rechazada';
  categoria_correcta?: string;
}

/** Sugerencia de cobranza (forma del action analizar-cobranza). */
export interface SugerenciaCobranza {
  cxc_id: string;
  cliente_nombre: string;
  monto: string;
  dias_vencida: number;
  prioridad: string;
  canal_sugerido: string;
  mensaje: string;
  motivo: string;
}

/** Sugerencia de reorden (forma del action analizar-reorden). */
export interface SugerenciaReorden {
  producto_id: string;
  nombre_producto: string;
  stock_disponible: number;
  cantidad_minima: number;
  estado: string;
  cantidad_sugerida: number;
  motivo: string;
  prioridad: string;
}

export interface AnalisisSugerenciasResponse<T> {
  sugerencias: T[];
  total: number;
}

/** Recomendaciones del PersonalizacionCapa2Agent (action analizar-personalizacion). */
export interface AnalisisPersonalizacion {
  flujo_documentos: unknown;
  listas_precios: unknown;
  credito_clientes: unknown;
}

/** Payload de POST predicciones/clasificar-gasto/. */
export interface ClasificarGastoPayload {
  gasto_id: string;
  aplicar?: boolean;
}

export interface ResultadoClasificacionGasto {
  prediccion_id: string | null;
  categoria: string;
  confianza: number;
  razonamiento: string;
  alternativas: unknown[];
  modelo_llm: string;
  aplicado: boolean;
  categoria_id: string | null;
}

/** Métricas del clasificador de gastos (action metricas-clasificador). */
export interface MetricasClasificador {
  total: number;
  evaluadas: number;
  precision: number;
  confianza_promedio: number;
  latencia_promedio_ms: number;
}

const BASE = '/agentes/predicciones';

// ── Servicio de predicciones ────────────────────────────────────────────────

export const prediccionesService = {
  /** Lista predicciones; filtrable por agente y/o resultado_humano. Normaliza a array. */
  getAll: async (params?: {
    agente?: Agente | string;
    resultado_humano?: ResultadoHumano | string;
  }): Promise<PrediccionAgente[]> => {
    const qs = new URLSearchParams();
    if (params?.agente) qs.set('agente', params.agente);
    if (params?.resultado_humano) qs.set('resultado_humano', params.resultado_humano);
    const query = qs.toString();
    const response = await get<PaginatedResponse<PrediccionAgente> | PrediccionAgente[]>(
      `${BASE}/${query ? '?' + query : ''}`,
    );
    return toList<PrediccionAgente>(response);
  },

  getById: async (id: string): Promise<PrediccionAgente> =>
    get<PrediccionAgente>(`${BASE}/${id}/`),

  /** Sugerencias activas (pendientes de revisión). `limite` opcional (default backend). */
  sugerenciasActivas: async (limite?: number): Promise<SugerenciaActiva[]> => {
    const qs = typeof limite === 'number' ? `?limite=${limite}` : '';
    const response = await get<SugerenciasActivasResponse>(`${BASE}/sugerencias-activas/${qs}`);
    return response.sugerencias ?? [];
  },

  /** Acepta o rechaza una sugerencia. */
  responder: async (id: string, payload: ResponderPayload): Promise<RespuestaPrediccion> => {
    const body: Record<string, unknown> = { accion: payload.accion };
    if (payload.comentario) body.comentario = payload.comentario;
    return post<RespuestaPrediccion>(`${BASE}/${id}/responder/`, body);
  },

  /** Evalúa una predicción (resultado humano + categoría correcta opcional). */
  evaluar: async (id: string, payload: EvaluarPayload): Promise<PrediccionAgente> => {
    const body: Record<string, unknown> = { resultado_humano: payload.resultado_humano };
    if (payload.categoria_correcta) body.categoria_correcta = payload.categoria_correcta;
    return patch<PrediccionAgente>(`${BASE}/${id}/evaluar/`, body);
  },

  /** Dispara el análisis de cobranza (read-only por defecto). */
  analizarCobranza: async (): Promise<AnalisisSugerenciasResponse<SugerenciaCobranza>> =>
    post<AnalisisSugerenciasResponse<SugerenciaCobranza>>(`${BASE}/analizar-cobranza/`, {}),

  /** Dispara el análisis de reorden de inventario (read-only por defecto). */
  analizarReorden: async (): Promise<AnalisisSugerenciasResponse<SugerenciaReorden>> =>
    post<AnalisisSugerenciasResponse<SugerenciaReorden>>(`${BASE}/analizar-reorden/`, {}),

  /** Dispara el análisis de personalización (Capa 2). */
  analizarPersonalizacion: async (): Promise<AnalisisPersonalizacion> =>
    post<AnalisisPersonalizacion>(`${BASE}/analizar-personalizacion/`, {}),

  /** Clasifica un gasto por id; `aplicar` opcional para escribir la categoría. */
  clasificarGasto: async (
    payload: ClasificarGastoPayload,
  ): Promise<ResultadoClasificacionGasto> => {
    const body: Record<string, unknown> = { gasto_id: payload.gasto_id };
    if (typeof payload.aplicar === 'boolean') body.aplicar = payload.aplicar;
    return post<ResultadoClasificacionGasto>(`${BASE}/clasificar-gasto/`, body);
  },

  /** Métricas de calidad del clasificador de gastos para la empresa. */
  metricasClasificador: async (): Promise<MetricasClasificador> =>
    get<MetricasClasificador>(`${BASE}/metricas-clasificador/`),
};
