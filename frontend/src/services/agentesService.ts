/**
 * Servicio del módulo de Agentes IA (M9 / Plan 05 P2-2).
 *
 * Cablea:
 *   - CRUD de predicciones (`/api/agentes/predicciones/`) y sus acciones custom
 *     (sugerencias activas, responder/evaluar, métricas del clasificador y disparo
 *     asíncrono vía Celery con HTTP 202 Accepted).
 *   - Consulta de ejecuciones (`/api/agentes/ejecuciones/`) y helper de polling
 *     cancelable con `AbortSignal`.
 *
 * El aislamiento multi-tenant lo aplica el backend; el front no envía `id_empresa`.
 * Cada payload se construye con whitelist explícita de campos (CTF-005 / CWE-915).
 */
import { get, post, patch } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Choices (espejo de AGENTE_CHOICES / RESULTADO_CHOICES / ESTADO_CHOICES) ────

/** Identificadores de agente (espejo de PrediccionAgente.AGENTE_CHOICES). */
export type Agente =
  | 'clasificador_gastos'
  | 'cobranza_estratega'
  | 'reorden_sugeridor'
  | 'personalizacion_capa2';

/** Resultado de la revisión humana (espejo de PrediccionAgente.RESULTADO_CHOICES). */
export type ResultadoHumano = 'pendiente' | 'aceptada' | 'rechazada';

/** Estado de una ejecución asíncrona (espejo de EjecucionAgente.ESTADO_CHOICES). */
export type EstadoEjecucion = 'pendiente' | 'ejecutando' | 'completado' | 'fallido';

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

export const ESTADOS_EJECUCION: readonly EstadoEjecucion[] = [
  'pendiente',
  'ejecutando',
  'completado',
  'fallido',
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

/** Ejecución asíncrona de un agente en Celery (espejo de EjecucionAgenteSerializer). */
export interface EjecucionAgente<TResultado = Record<string, unknown>> {
  id_ejecucion: string;
  agente: Agente | string;
  estado: EstadoEjecucion;
  celery_task_id: string;
  parametros: Record<string, unknown>;
  resultado: TResultado;
  mensaje_error: string;
  iniciado_por: string | null;
  fecha_creacion: string;
  fecha_inicio: string | null;
  fecha_fin: string | null;
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

/** Sugerencia de cobranza (resultado de ejecución cobranza_estratega). */
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

/** Sugerencia de reorden (resultado de ejecución reorden_sugeridor). */
export interface SugerenciaReorden {
  producto_id: string;
  nombre_producto: string;
  stock_disponible: string | number;
  cantidad_minima: string | number;
  estado: string;
  cantidad_sugerida: string | number;
  motivo: string;
  prioridad: string;
}

export interface AnalisisSugerenciasResponse<T> {
  sugerencias: T[];
  total: number;
}

/** Recomendaciones del PersonalizacionCapa2Agent (resultado de ejecución). */
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
  evaluadas?: number;
  precision: number | null;
  confianza_promedio: number | null;
  latencia_promedio_ms?: number;
}

/** Evento persistido de consumo y costo LLM por tenant (Plan 05 P2-3). */
export interface ConsumoLLM {
  id_consumo: string;
  id_empresa: string | null;
  proveedor: string;
  uso: string;
  modelo: string;
  tokens_entrada: number;
  tokens_salida: number;
  costo_estimado_usd: string;
  latencia_ms: number;
  creado_en: string;
}

export interface ConsumoLLMPorModelo {
  modelo: string;
  llamadas: number;
  tokens_entrada_total: number;
  tokens_salida_total: number;
  costo_total_usd: string;
}

export interface ConsumoLLMPorUso {
  uso: string;
  llamadas: number;
  tokens_entrada_total: number;
  tokens_salida_total: number;
  costo_total_usd: string;
}

/** Resumen agregado de consumo LLM (`/api/agentes/consumo-llm/resumen/`). */
export interface ConsumoLLMResumen {
  llamadas: number;
  tokens_entrada_total: number;
  tokens_salida_total: number;
  costo_total_usd: string;
  latencia_promedio_ms: number;
  por_modelo: ConsumoLLMPorModelo[];
  por_uso: ConsumoLLMPorUso[];
}

export interface ConsumoLLMFiltros {
  modelo?: string;
  uso?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
}

export interface EsperarEjecucionOptions<T = Record<string, unknown>> {
  intervalMs?: number;
  maxIntentos?: number;
  signal?: AbortSignal;
  onEstado?: (ejecucion: EjecucionAgente<T>) => void;
}

const BASE = '/agentes/predicciones';
const EJECUCIONES_BASE = '/agentes/ejecuciones';
const CONSUMO_LLM_BASE = '/agentes/consumo-llm';

function buildConsumoQuery(filtros?: ConsumoLLMFiltros): string {
  const qs = new URLSearchParams();
  if (filtros?.modelo) qs.set('modelo', filtros.modelo);
  if (filtros?.uso) qs.set('uso', filtros.uso);
  if (filtros?.fecha_desde) qs.set('fecha_desde', filtros.fecha_desde);
  if (filtros?.fecha_hasta) qs.set('fecha_hasta', filtros.fecha_hasta);
  return qs.toString();
}

function abortError(): DOMException {
  return new DOMException('Operación cancelada.', 'AbortError');
}

function sleepCancelable(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

// ── Servicio de predicciones y ejecuciones ────────────────────────────────────

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

  /** Encola el análisis de cobranza en Celery (HTTP 202 Accepted). */
  analizarCobranza: async (payload?: {
    persistir?: boolean;
  }): Promise<EjecucionAgente<AnalisisSugerenciasResponse<SugerenciaCobranza>>> => {
    const body: Record<string, unknown> = {};
    if (typeof payload?.persistir === 'boolean') body.persistir = payload.persistir;
    return post<EjecucionAgente<AnalisisSugerenciasResponse<SugerenciaCobranza>>>(
      `${BASE}/analizar-cobranza/`,
      body,
    );
  },

  /** Encola el análisis de reorden de inventario en Celery (HTTP 202 Accepted). */
  analizarReorden: async (payload?: {
    solo_alertas?: boolean;
    persistir?: boolean;
  }): Promise<EjecucionAgente<AnalisisSugerenciasResponse<SugerenciaReorden>>> => {
    const body: Record<string, unknown> = {};
    if (typeof payload?.solo_alertas === 'boolean') body.solo_alertas = payload.solo_alertas;
    if (typeof payload?.persistir === 'boolean') body.persistir = payload.persistir;
    return post<EjecucionAgente<AnalisisSugerenciasResponse<SugerenciaReorden>>>(
      `${BASE}/analizar-reorden/`,
      body,
    );
  },

  /** Encola el análisis de personalización Capa 2 en Celery (HTTP 202 Accepted). */
  analizarPersonalizacion: async (): Promise<EjecucionAgente<AnalisisPersonalizacion>> =>
    post<EjecucionAgente<AnalisisPersonalizacion>>(`${BASE}/analizar-personalizacion/`, {}),

  /** Encola la clasificación de un gasto en Celery (HTTP 202 Accepted). */
  clasificarGasto: async (
    payload: ClasificarGastoPayload,
  ): Promise<EjecucionAgente<ResultadoClasificacionGasto>> => {
    const body: Record<string, unknown> = { gasto_id: payload.gasto_id };
    if (typeof payload.aplicar === 'boolean') body.aplicar = payload.aplicar;
    return post<EjecucionAgente<ResultadoClasificacionGasto>>(`${BASE}/clasificar-gasto/`, body);
  },

  /** Lista ejecuciones asíncronas de agentes para el tenant actual. */
  listarEjecuciones: async (params?: {
    agente?: Agente | string;
    estado?: EstadoEjecucion | string;
  }): Promise<EjecucionAgente[]> => {
    const qs = new URLSearchParams();
    if (params?.agente) qs.set('agente', params.agente);
    if (params?.estado) qs.set('estado', params.estado);
    const query = qs.toString();
    const response = await get<PaginatedResponse<EjecucionAgente> | EjecucionAgente[]>(
      `${EJECUCIONES_BASE}/${query ? '?' + query : ''}`,
    );
    return toList<EjecucionAgente>(response);
  },

  /** Consulta el estado y resultado de una ejecución específica. */
  obtenerEjecucion: async <T = Record<string, unknown>>(
    id: string,
    signal?: AbortSignal,
  ): Promise<EjecucionAgente<T>> =>
    signal
      ? get<EjecucionAgente<T>>(`${EJECUCIONES_BASE}/${id}/`, { signal })
      : get<EjecucionAgente<T>>(`${EJECUCIONES_BASE}/${id}/`),

  /**
   * Realiza polling acotado y cancelable (`AbortSignal`) sobre una ejecución
   * hasta alcanzar un estado terminal (`completado` o `fallido`).
   */
  esperarEjecucion: async <T = Record<string, unknown>>(
    ejecucionInicialOrId: EjecucionAgente<T> | string,
    options?: EsperarEjecucionOptions<T>,
  ): Promise<EjecucionAgente<T>> => {
    const intervalMs = options?.intervalMs ?? 1000;
    const maxIntentos = options?.maxIntentos ?? 60;
    const signal = options?.signal;

    let actual: EjecucionAgente<T>;
    if (typeof ejecucionInicialOrId === 'string') {
      if (signal?.aborted) throw abortError();
      actual = await prediccionesService.obtenerEjecucion<T>(ejecucionInicialOrId, signal);
    } else {
      actual = ejecucionInicialOrId;
    }
    options?.onEstado?.(actual);

    for (let intento = 0; intento < maxIntentos; intento += 1) {
      if (actual.estado === 'completado' || actual.estado === 'fallido') {
        return actual;
      }
      await sleepCancelable(intervalMs, signal);
      if (signal?.aborted) throw abortError();
      actual = await prediccionesService.obtenerEjecucion<T>(actual.id_ejecucion, signal);
      options?.onEstado?.(actual);
    }

    if (actual.estado === 'completado' || actual.estado === 'fallido') {
      return actual;
    }
    throw new Error('Tiempo de espera agotado consultando la ejecución del agente.');
  },

  /** Métricas de calidad del clasificador de gastos para la empresa. */
  metricasClasificador: async (): Promise<MetricasClasificador> =>
    get<MetricasClasificador>(`${BASE}/metricas-clasificador/`),

  /** Lista registros históricos de consumo LLM del tenant. */
  listarConsumoLLM: async (filtros?: ConsumoLLMFiltros): Promise<ConsumoLLM[]> => {
    const query = buildConsumoQuery(filtros);
    const response = await get<PaginatedResponse<ConsumoLLM> | ConsumoLLM[]>(
      `${CONSUMO_LLM_BASE}/${query ? '?' + query : ''}`,
    );
    return toList<ConsumoLLM>(response);
  },

  /** Obtiene el resumen agregado de tokens y costo estimado USD del tenant. */
  obtenerResumenConsumoLLM: async (filtros?: ConsumoLLMFiltros): Promise<ConsumoLLMResumen> => {
    const query = buildConsumoQuery(filtros);
    return get<ConsumoLLMResumen>(`${CONSUMO_LLM_BASE}/resumen/${query ? '?' + query : ''}`);
  },
};

export const listarConsumoLLM = prediccionesService.listarConsumoLLM;
export const obtenerResumenConsumoLLM = prediccionesService.obtenerResumenConsumoLLM;
