import { useSyncExternalStore } from 'react';

/**
 * Estado de conexión del navegador (offline Nivel 1, ADR-001).
 *
 * Se basa en `navigator.onLine` + eventos `online`/`offline` vía
 * `useSyncExternalStore` (sin estado duplicado ni efectos). TanStack Query
 * escucha estos mismos eventos con su `onlineManager`, así que el banner y
 * la pausa/reanudación de queries/mutaciones quedan sincronizados.
 */
function subscribe(onStoreChange: () => void): () => void {
  window.addEventListener('online', onStoreChange);
  window.addEventListener('offline', onStoreChange);
  return () => {
    window.removeEventListener('online', onStoreChange);
    window.removeEventListener('offline', onStoreChange);
  };
}

function getSnapshot(): boolean {
  return typeof navigator === 'undefined' ? true : navigator.onLine;
}

export function useOnlineStatus(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => true);
}
