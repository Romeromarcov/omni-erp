/**
 * Cliente del pull de deltas para la réplica local offline (CTF-008 Nivel 2).
 *
 * Consume `GET /api/sync/pull/` (backend `apps/sync`): trae los registros de
 * catálogo de la empresa creados/modificados desde un cursor `desde`. El
 * servidor devuelve `server_time`, que es el cursor autoritativo para el
 * siguiente pull (evita el clock-skew del cliente).
 *
 * `pullAllDeltas` pagina hasta agotar `has_more` avanzando el cursor al máximo
 * `fecha_actualizacion` visto y deduplicando el registro del borde por PK
 * (el backend usa `>=` inclusivo).
 */
import { get, post, type HttpError } from './api';

/** Entidades sincronizables expuestas por el backend (registry de apps/sync). */
export type SyncEntity =
  | 'productos'
  | 'categorias_producto'
  | 'unidades_medida'
  | 'clientes'
  | 'variantes_producto';

export type SyncEditableEntity = 'clientes' | 'productos' | 'categorias_producto';

export interface SyncMutationPayload {
  entity: SyncEditableEntity;
  id: string;
  expected_fecha_actualizacion: string;
  cambios: Record<string, string | boolean | null>;
}

export interface SyncPushSuccessResponse {
  entity: SyncEditableEntity;
  id: string;
  server_time: string;
  registro: SyncRecord;
}

export interface SyncConflictPayload {
  error: string;
  codigo: 'CONFLICTO_VERSION';
  entity: SyncEditableEntity;
  id: string;
  registro_servidor: SyncRecord;
  index?: number;
}

export type SyncPushResult =
  | { ok: true; data: SyncPushSuccessResponse }
  | { ok: false; conflicto: SyncConflictPayload };

export interface SyncRecord {
  fecha_actualizacion: string;
  activo: boolean;
  [key: string]: unknown;
}

export interface SyncPullResponse<T extends SyncRecord = SyncRecord> {
  entity: SyncEntity;
  server_time: string;
  count: number;
  has_more: boolean;
  results: T[];
}

export interface PullOptions {
  /** Cursor ISO 8601; omitir para una carga inicial completa. */
  desde?: string;
  /** Tamaño de página (backend: máx. 1000, def. 500). */
  limite?: number;
}

/** Un único pull (una página) de una entidad. */
export async function pullDeltas<T extends SyncRecord = SyncRecord>(
  entity: SyncEntity,
  options: PullOptions = {},
): Promise<SyncPullResponse<T>> {
  const params = new URLSearchParams({ entity });
  if (options.desde) params.set('desde', options.desde);
  if (options.limite != null) params.set('limite', String(options.limite));
  return get<SyncPullResponse<T>>(`/sync/pull/?${params.toString()}`);
}

/** PK por entidad, para deduplicar el registro del borde entre páginas.
 * Map (no objeto plano) para no disparar `security/detect-object-injection`. */
const PK_FIELD = new Map<SyncEntity, string>([
  ['productos', 'id_producto'],
  ['categorias_producto', 'id_categoria_producto'],
  ['unidades_medida', 'id_unidad_medida'],
  ['clientes', 'id_cliente'],
  ['variantes_producto', 'id_variante'],
]);

export interface PullAllResult<T extends SyncRecord = SyncRecord> {
  /** Registros únicos acumulados (último estado por PK). */
  records: T[];
  /** Cursor a guardar para el próximo sync incremental. */
  serverTime: string;
}

/**
 * Pagina hasta agotar `has_more`. Tope de páginas defensivo para no colgarse si
 * el servidor reporta `has_more` de forma inconsistente.
 */
export async function pullAllDeltas<T extends SyncRecord = SyncRecord>(
  entity: SyncEntity,
  options: PullOptions = {},
  maxPaginas = 1000,
): Promise<PullAllResult<T>> {
  const pk = PK_FIELD.get(entity) as string;
  const porPk = new Map<unknown, T>();
  let desde = options.desde;
  let serverTime = desde ?? '';

  for (let i = 0; i < maxPaginas; i++) {
    const page = await pullDeltas<T>(entity, { desde, limite: options.limite });
    serverTime = page.server_time;
    // eslint-disable-next-line security/detect-object-injection -- FP: `pk` es un nombre de campo constante de PK_FIELD, no input de usuario
    for (const r of page.results) porPk.set(r[pk], r);
    if (!page.has_more || page.results.length === 0) break;
    // Avanzar el cursor al máximo fecha_actualizacion de la página.
    desde = page.results.reduce(
      (max, r) => (r.fecha_actualizacion > max ? r.fecha_actualizacion : max),
      page.results[0].fecha_actualizacion,
    );
  }
  return { records: [...porPk.values()], serverTime };
}

/**
 * Envía una mutación optimista a `POST /api/sync/push/`.
 * Ante HTTP 409 (`CONFLICTO_VERSION`) retorna `{ ok: false, conflicto }` con
 * `registro_servidor` para que la UI muestre local vs servidor y permita reintentar.
 */
export async function pushOptimisticUpdate(
  payload: SyncMutationPayload,
  idempotencyKey?: string,
): Promise<SyncPushResult> {
  const headers: Record<string, string> = {};
  if (idempotencyKey) {
    headers['Idempotency-Key'] = idempotencyKey;
  }
  try {
    const data = await post<SyncPushSuccessResponse>(
      '/sync/push/',
      payload as unknown as Record<string, unknown>,
      Object.keys(headers).length > 0 ? { headers } : undefined,
    );
    return { ok: true, data };
  } catch (err) {
    const httpErr = err as HttpError;
    if (httpErr.status === 409) {
      const parsed = JSON.parse(httpErr.message) as Partial<SyncConflictPayload>;
      if (parsed.codigo === 'CONFLICTO_VERSION' && parsed.registro_servidor) {
        return { ok: false, conflicto: parsed as SyncConflictPayload };
      }
    }
    throw err;
  }
}
