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

export interface OutboxSale {
  /** Clave de idempotencia estable; el backend deduplica por ella. */
  idempotencyKey: string;
  /** Endpoint relativo, p. ej. "/ventas/notas-venta/". */
  endpoint: string;
  /** Cuerpo del POST tal cual se enviaría online. */
  payload: Record<string, unknown>;
  /** Epoch ms en que se encoló (orden FIFO y diagnóstico). */
  createdAt: number;
}

export interface FlushResult {
  enviados: number;
  /** Rechazos permanentes (4xx): se descartan de la cola, no reintentables. */
  rechazados: number;
  /** Entradas que quedan para el próximo intento (error de red / 5xx). */
  pendientes: number;
  errores: { idempotencyKey: string; status?: number; mensaje: string }[];
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

/** Encola una venta para reenvío diferido. */
export async function enqueueSale(entry: OutboxSale): Promise<void> {
  const cola = await storage.read();
  cola.push(entry);
  await storage.write(cola);
}

/** Lista las ventas pendientes en orden FIFO. */
export async function listPending(): Promise<OutboxSale[]> {
  return storage.read();
}

/** Vacía la cola (uso en tests / reset explícito). */
export async function clearOutbox(): Promise<void> {
  await storage.write([]);
}

function statusDe(err: unknown): number | undefined {
  if (err && typeof err === 'object' && 'status' in err) {
    const s = (err as { status?: unknown }).status;
    if (typeof s === 'number') return s;
  }
  return undefined;
}

function mensajeDe(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

/**
 * Reenvía las ventas pendientes en orden. Un 4xx (rechazo permanente) se
 * descarta; un error de red o 5xx (transitorio) detiene el flush y conserva el
 * resto para el próximo intento (evita perder el orden y machacar el servidor).
 */
export async function flushOutbox(poster: SalePoster): Promise<FlushResult> {
  const cola = await storage.read();
  const resultado: FlushResult = { enviados: 0, rechazados: 0, pendientes: 0, errores: [] };
  let cortadoEn = cola.length; // índice donde un error transitorio detuvo el flush

  for (const [idx, venta] of cola.entries()) {
    try {
      await poster(venta.endpoint, venta.payload, venta.idempotencyKey);
      resultado.enviados += 1;
    } catch (err) {
      const status = statusDe(err);
      if (status !== undefined && status >= 400 && status < 500) {
        // Permanente: nunca va a pasar; se descarta y se reporta.
        resultado.rechazados += 1;
        resultado.errores.push({
          idempotencyKey: venta.idempotencyKey,
          status,
          mensaje: mensajeDe(err),
        });
        continue;
      }
      // Transitorio: detener; esta y las siguientes quedan pendientes.
      resultado.errores.push({
        idempotencyKey: venta.idempotencyKey,
        status,
        mensaje: mensajeDe(err),
      });
      cortadoEn = idx;
      break;
    }
  }

  // La cola restante = lo no procesado (desde el corte transitorio, si hubo).
  const restantes = cola.slice(cortadoEn);
  await storage.write(restantes);
  resultado.pendientes = restantes.length;
  return resultado;
}
