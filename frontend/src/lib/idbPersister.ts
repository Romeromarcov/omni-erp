import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';

/**
 * Persistencia del caché de TanStack Query en IndexedDB — offline Nivel 1
 * "réplica local" (ADR-001 / Plan Maestro §5.2-ter).
 *
 * Sin esto el caché vive solo en memoria: un reload o reinicio del navegador
 * estando sin red pierde todos los datos y la app queda inutilizable hasta que
 * vuelva la conexión. Persistiendo a IndexedDB, las consultas ya cargadas
 * sobreviven a reloads/reinicios y la app abre con datos (marcados como "sin
 * actualizar" por el banner) aunque arranque offline.
 *
 * Implementación deliberadamente sin dependencias nuevas de IndexedDB: usa
 * `idb` (ya presente, transitiva) detrás de un almacén clave-valor de una sola
 * entrada. En entornos sin IndexedDB (tests jsdom, SSR) cae a un almacén en
 * memoria para no romper.
 */

const DB_NAME = 'omni-erp-cache';
const STORE_NAME = 'tanstack-query';

interface AsyncStorage {
  getItem: (key: string) => Promise<string | null>;
  setItem: (key: string, value: string) => Promise<void>;
  removeItem: (key: string) => Promise<void>;
}

function memoryStorage(): AsyncStorage {
  const map = new Map<string, string>();
  return {
    getItem: async (k) => map.get(k) ?? null,
    setItem: async (k, v) => {
      map.set(k, v);
    },
    removeItem: async (k) => {
      map.delete(k);
    },
  };
}

/* v8 ignore start -- requiere IndexedDB real (navegador); se verifica en E2E /
   prueba manual de corte de red, no en jsdom (sin IndexedDB). */
function idbStorage(): AsyncStorage {
  // Import perezoso: solo se carga `idb` cuando hay IndexedDB real.
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
    getItem: async (key) => (await (await dbPromise).get(STORE_NAME, key)) ?? null,
    setItem: async (key, value) => {
      await (await dbPromise).put(STORE_NAME, value, key);
    },
    removeItem: async (key) => {
      await (await dbPromise).delete(STORE_NAME, key);
    },
  };
}
/* v8 ignore stop */

const hasIndexedDB = typeof globalThis !== 'undefined' && 'indexedDB' in globalThis && globalThis.indexedDB != null;

const storage: AsyncStorage = hasIndexedDB ? idbStorage() : memoryStorage();

/** Clave única bajo la que el persister guarda el caché serializado. */
export const PERSIST_KEY = 'omni-erp-query-cache';

export const idbPersister = createAsyncStoragePersister({
  storage,
  key: PERSIST_KEY,
  // Throttle de escritura: agrupa ráfagas de actualizaciones del caché.
  throttleTime: 1000,
});

/**
 * Borra el caché persistido. Debe llamarse en el logout: en un dispositivo
 * compartido, los datos de negocio de un usuario/tenant no pueden quedar
 * disponibles para el siguiente (multi-tenant, R-CODE-1).
 */
export async function clearPersistedQueryCache(): Promise<void> {
  try {
    await storage.removeItem(PERSIST_KEY);
  } catch {
    // best-effort: si IndexedDB falla, el caché en memoria se descarta igual
    // al recargar; no bloquear el logout por esto.
  }
}
