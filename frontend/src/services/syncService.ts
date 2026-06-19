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
import { get } from './api';

/** Entidades sincronizables expuestas por el backend (registry de apps/sync). */
export type SyncEntity =
  | 'productos'
  | 'categorias_producto'
  | 'unidades_medida'
  | 'clientes'
  | 'variantes_producto';

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
    // `pk` es un nombre de campo constante de PK_FIELD (no input de usuario).
    // eslint-disable-next-line security/detect-object-injection
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
