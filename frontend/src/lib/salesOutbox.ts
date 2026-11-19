/**
 * Outbox de ventas POS creadas sin red — CTF-008 Nivel 2 (mitad cliente).
 *
 * Cuando el POST de una venta falla por falta de conexión, la venta se encola
 * aquí (persistida en IndexedDB para sobrevivir reloads/reinicios) y se reenvía
 * al recuperar la red. Cada entrada lleva una `idempotencyKey` ESTABLE generada
 * al encolar: el reenvío reusa esa clave y el backend deduplica
 * (`apps/core/idempotency.py`, scope `ventas:nota-venta-create`), por lo que un
 * reintento NUNCA duplica la venta ni sus efectos (garantía probada en el
 * backend, ver tests/api/test_sync_ventas_idempotente.py).
 *
 * Sin dependencias nuevas: usa `idb` (ya presente, transitiva) con fallback a
 * memoria en entornos sin IndexedDB (tests jsdom, SSR), igual criterio que
 * `idbPersister.ts`.
 */

const DB_NAME = 'omni-erp-outbox';
const STORE_NAME = 'ventas-pendientes';
const KEY = 'cola';

export type OutboxSaleEstado = 'PENDIENTE' | 'SINCRONIZADA' | 'REQUIERE_REVISION';

export interface OutboxSale {
  /** Clave de idempotencia estable; el backend deduplica por ella. */
  idempotencyKey: string;
  /** Endpoint relativo, p. ej. "/sync/push/ventas/". */
  endpoint: string;
  /** Cuerpo del POST tal cual se enviaría online. */
  payload: Record<string, unknown>;
  /** Epoch ms en que se encoló (orden FIFO y diagnóstico). */
  createdAt: number;
  /** Estado del ciclo offline (por defecto 'PENDIENTE'). */
  estado?: OutboxSaleEstado;
  /** Folio provisional local mientras espera confirmación del servidor. */
  folioProvisional?: string;
  /** Total provisional local mostrado en cola. */
  totalProvisional?: string;
  /** Moneda de despliegue asociada al total provisional. */
  codigoIso?: string;
  /** ID definitivo devuelto por el servidor al sincronizar. */
  idNotaVenta?: string;
  /** Número definitivo devuelto por el servidor al sincronizar. */
  numeroNota?: string;
  /** Epoch ms en que se confirmó la sincronización. */
  syncedAt?: number;
  /** Indica si la venta sincronizó usando stock negativo permitido por tenant. */
  alertaStockNegativo?: boolean;
  /** Detalle del rechazo permanente cuando pasa a 'REQUIERE_REVISION'. */
  errorMensaje?: string;
  /** Código de rechazo del servidor (p. ej. 'REQUIERE_REVISION'). */
  errorCodigo?: string;
  /** Código HTTP del rechazo permanente (4xx). */
  errorStatus?: number;
}

export interface FlushSincronizada {
  idempotencyKey: string;
  idNotaVenta?: string;
  numeroNota?: string;
  alertaStockNegativo?: boolean;
}

export interface FlushError {
  idempotencyKey: string;
  status?: number;
  codigo?: string;
  mensaje: string;
}

export interface FlushResult {
  enviados: number;
  /** Rechazos permanentes (4xx): pasan a REQUIERE_REVISION sin reintentar en bucle. */
  rechazados: number;
  /** Entradas que quedan PENDIENTE para el próximo intento (error de red / 5xx). */
  pendientes: number;
  errores: FlushError[];
  sincronizadas?: FlushSincronizada[];
}

/** Reenvía una venta; resuelve con la respuesta o lanza (con `.status` si es HTTP). */
export type SalePoster = (
  endpoint: string,
  payload: Record<string, unknown>,
  idempotencyKey: string,
) => Promise<unknown>;

interface KVStorage {
  read: () => Promise<OutboxSale[]>;
  write: (cola: OutboxSale[]) => Promise<void>;
}

function memoryStorage(): KVStorage {
  let cola: OutboxSale[] = [];
  return {
    read: async () => cola.slice(),
    write: async (next) => {
      cola = next.slice();
    },
  };
}

/* v8 ignore start -- requiere IndexedDB real (navegador); se cubre en E2E /
   prueba manual de corte de red, no en jsdom (sin IndexedDB). */
function idbStorage(): KVStorage {
  const dbPromise = import('idb').then(({ openDB }) =>
    openDB(DB_NAME, 1, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME);
        }
      },
    }),
  );
  return {
    read: async () => (await (await dbPromise).get(STORE_NAME, KEY)) ?? [],
    write: async (cola) => {
      await (await dbPromise).put(STORE_NAME, cola, KEY);
    },
  };
}
/* v8 ignore stop */

function hasIndexedDB(): boolean {
  try {
    return typeof indexedDB !== 'undefined' && indexedDB !== null;
  } catch {
    return false;
  }
}

// Almacén único por módulo (memoria en tests; IndexedDB en navegador).
const storage: KVStorage = hasIndexedDB() ? idbStorage() : memoryStorage();

// Época monotónica incrementada en clearOutbox(): invalida cualquier flush
// en vuelo iniciado antes de la purga (evita resucitar ventas tras logout).
let clearEpoch = 0;
// Mutex serializado para operaciones rápidas read-modify-write sobre storage.
let storageQueue: Promise<void> = Promise.resolve();
// Mutex separado para serializar corridas de flushOutbox sin bloquear enqueue/clear.
let flushQueue: Promise<void> = Promise.resolve();

function enqueueOn<T>(getTail: () => Promise<void>, setTail: (next: Promise<void>) => void, fn: () => Promise<T>): Promise<T> {
  const run = getTail().then(fn, fn);
  setTail(
    run.then(
      () => undefined,
      () => undefined,
    ),
  );
  return run;
}

function withStorageLock<T>(fn: () => Promise<T>): Promise<T> {
  return enqueueOn(
    () => storageQueue,
    (next) => {
      storageQueue = next;
    },
    fn,
  );
}

function withFlushLock<T>(fn: () => Promise<T>): Promise<T> {
  return enqueueOn(
    () => flushQueue,
    (next) => {
      flushQueue = next;
    },
    fn,
  );
}

function estadoDe(entry: OutboxSale): OutboxSaleEstado {
  return entry.estado ?? 'PENDIENTE';
}

/** Encola una venta para reenvío diferido (idempotente por idempotencyKey). */
export async function enqueueSale(entry: OutboxSale): Promise<void> {
  return withStorageLock(async () => {
    const cola = await storage.read();
    if (cola.some((v) => v.idempotencyKey === entry.idempotencyKey)) {
      return;
    }
    cola.push({ ...entry, estado: estadoDe(entry) });
    await storage.write(cola);
  });
}

/** Lista las ventas pendientes de envío en orden FIFO. */
export async function listPending(): Promise<OutboxSale[]> {
  return withStorageLock(async () => {
    const cola = await storage.read();
    return cola.filter((v) => estadoDe(v) === 'PENDIENTE').map((v) => ({ ...v, estado: 'PENDIENTE' }));
  });
}

/** Lista todas las entradas del outbox (pendientes, sincronizadas y en revisión). */
export async function listOutboxItems(): Promise<OutboxSale[]> {
  return withStorageLock(async () => {
    const cola = await storage.read();
    return cola.map((v) => ({ ...v, estado: estadoDe(v) }));
  });
}

/** Descarta explícitamente una entrada del outbox por su idempotencyKey. */
export async function discardOutboxItem(idempotencyKey: string): Promise<void> {
  return withStorageLock(async () => {
    const cola = await storage.read();
    await storage.write(cola.filter((v) => v.idempotencyKey !== idempotencyKey));
  });
}

/** Reencola una entrada en 'REQUIERE_REVISION' para volver a intentar su envío. */
export async function retryOutboxItem(idempotencyKey: string): Promise<void> {
  return withStorageLock(async () => {
    const cola = await storage.read();
    const next = cola.map((v) =>
      v.idempotencyKey === idempotencyKey
        ? {
            ...v,
            estado: 'PENDIENTE' as const,
            errorMensaje: undefined,
            errorCodigo: undefined,
            errorStatus: undefined,
          }
        : v,
    );
    await storage.write(next);
  });
}

/** Limpia solo las ventas ya sincronizadas preservando pendientes y en revisión. */
export async function clearSyncedOutboxItems(): Promise<void> {
  return withStorageLock(async () => {
    const cola = await storage.read();
    await storage.write(cola.filter((v) => estadoDe(v) !== 'SINCRONIZADA'));
  });
}

/** Vacía toda la cola y registros locales del outbox (uso en logout / reset). */
export async function clearOutbox(): Promise<void> {
  clearEpoch += 1;
  return withStorageLock(async () => {
    clearEpoch += 1;
    await storage.write([]);
  });
}

function statusDe(err: unknown): number | undefined {
  if (err && typeof err === 'object' && 'status' in err) {
    const s = (err as { status?: unknown }).status;
    if (typeof s === 'number') return s;
  }
  return undefined;
}

function detalleError(err: unknown): { mensaje: string; codigo?: string } {
  if (!(err instanceof Error)) return { mensaje: String(err) };
  try {
    const parsed: unknown = JSON.parse(err.message);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const obj = parsed as Record<string, unknown>;
      const codigo = typeof obj.codigo === 'string' ? obj.codigo : undefined;
      const msg =
        (typeof obj.error === 'string' && obj.error) ||
        (typeof obj.detail === 'string' && obj.detail) ||
        err.message;
      return { mensaje: msg, codigo };
    }
  } catch {
    // Error no-JSON (p. ej. TypeError o Error simple): usar message tal cual.
  }
  return { mensaje: err.message };
}

function extraerSyncInfo(resp: unknown): {
  idNotaVenta?: string;
  numeroNota?: string;
  alertaStockNegativo?: boolean;
} {
  if (!resp || typeof resp !== 'object') return {};
  const obj = resp as Record<string, unknown>;
  const idNotaVenta = typeof obj.id_nota_venta === 'string' ? obj.id_nota_venta : undefined;
  const numeroNota =
    typeof obj.numero_nota === 'string'
      ? obj.numero_nota
      : typeof obj.numero_nota_venta === 'string'
        ? obj.numero_nota_venta
        : undefined;
  const alertaStockNegativo = obj.alerta_stock_negativo === true;
  return { idNotaVenta, numeroNota, alertaStockNegativo };
}

async function aplicarTransicionItem(
  idempotencyKey: string,
  epochInicial: number,
  transform: (item: OutboxSale) => OutboxSale,
): Promise<{ abortado: boolean; aplicado: boolean }> {
  return withStorageLock(async () => {
    if (clearEpoch !== epochInicial) {
      return { abortado: true, aplicado: false };
    }
    const colaActual = await storage.read();
    let encontrado = false;
    const siguienteCola = colaActual.map((item) => {
      if (item.idempotencyKey !== idempotencyKey) return item;
      encontrado = true;
      return transform(item);
    });
    if (encontrado) {
      await storage.write(siguienteCola);
    }
    return { abortado: false, aplicado: encontrado };
  });
}

/**
 * Reenvía las ventas pendientes en orden FIFO de forma atómica por ítem.
 * - Preserva ventas encoladas concurrentemente mientras `poster` está en vuelo.
 * - Si `clearOutbox()` corre durante un envío, aborta al detectar cambio de época
 *   sin resucitar registros ni escribir sobre la cola nueva.
 * - 2xx: pasa a 'SINCRONIZADA' con el mapeo idNotaVenta / numeroNota del servidor.
 * - 4xx (rechazo permanente): pasa a 'REQUIERE_REVISION' sin reintentar en bucle.
 * - Error de red o 5xx (transitorio): detiene el flush y conserva las pendientes.
 */
export async function flushOutbox(poster: SalePoster): Promise<FlushResult> {
  const epochInicial = clearEpoch;
  return withFlushLock(async () => {
    const sincronizadas: FlushSincronizada[] = [];
    const resultado: FlushResult = {
      enviados: 0,
      rechazados: 0,
      pendientes: 0,
      errores: [],
      sincronizadas,
    };
    const intentadas = new Set<string>();

    while (true) {
      const paso = await withStorageLock(async () => {
        if (clearEpoch !== epochInicial) {
          return { abortado: true as const, venta: null };
        }
        const cola = await storage.read();
        const venta =
          cola.find((v) => estadoDe(v) === 'PENDIENTE' && !intentadas.has(v.idempotencyKey)) ?? null;
        return { abortado: false as const, venta };
      });

      if (paso.abortado) {
        resultado.pendientes = 0;
        return resultado;
      }
      if (!paso.venta) {
        break;
      }

      const venta = paso.venta;
      intentadas.add(venta.idempotencyKey);

      try {
        const resp = await poster(venta.endpoint, venta.payload, venta.idempotencyKey);
        const info = extraerSyncInfo(resp);
        const tx = await aplicarTransicionItem(venta.idempotencyKey, epochInicial, (actual) => ({
          ...actual,
          estado: 'SINCRONIZADA',
          idNotaVenta: info.idNotaVenta,
          numeroNota: info.numeroNota,
          alertaStockNegativo: info.alertaStockNegativo,
          syncedAt: Date.now(),
          errorMensaje: undefined,
          errorCodigo: undefined,
          errorStatus: undefined,
        }));
        if (tx.abortado) {
          resultado.pendientes = 0;
          return resultado;
        }
        if (tx.aplicado) {
          resultado.enviados += 1;
          sincronizadas.push({
            idempotencyKey: venta.idempotencyKey,
            idNotaVenta: info.idNotaVenta,
            numeroNota: info.numeroNota,
            alertaStockNegativo: info.alertaStockNegativo,
          });
        }
      } catch (err) {
        const status = statusDe(err);
        const { mensaje, codigo } = detalleError(err);
        if (status !== undefined && status >= 400 && status < 500) {
          // Permanente: no reintentar en bucle; pasa a REQUIERE_REVISION visible para el cajero.
          const tx = await aplicarTransicionItem(venta.idempotencyKey, epochInicial, (actual) => ({
            ...actual,
            estado: 'REQUIERE_REVISION',
            errorMensaje: mensaje,
            errorCodigo: codigo,
            errorStatus: status,
          }));
          if (tx.abortado) {
            resultado.pendientes = 0;
            return resultado;
          }
          if (tx.aplicado) {
            resultado.rechazados += 1;
            resultado.errores.push({
              idempotencyKey: venta.idempotencyKey,
              status,
              codigo,
              mensaje,
            });
          }
          continue;
        }
        // Transitorio: detener; esta y las siguientes siguen PENDIENTE.
        resultado.errores.push({
          idempotencyKey: venta.idempotencyKey,
          status,
          codigo,
          mensaje,
        });
        break;
      }
    }

    resultado.pendientes = await withStorageLock(async () => {
      if (clearEpoch !== epochInicial) return 0;
      const colaFinal = await storage.read();
      return colaFinal.filter((v) => estadoDe(v) === 'PENDIENTE').length;
    });
    return resultado;
  });
}
