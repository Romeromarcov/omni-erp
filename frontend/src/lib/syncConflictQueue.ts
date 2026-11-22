/**
 * Cola persistente de conflictos de concurrencia optimista (`409 CONFLICTO_VERSION`) — CTF-008 Nivel 2.
 */
import {
  pushOptimisticUpdate,
  type SyncConflictPayload,
  type SyncMutationPayload,
  type SyncPushResult,
} from '../services/syncService';

export const SYNC_CONFLICTS_STORAGE_KEY = 'omni_sync_conflicts_v1';

export interface SyncConflictItem {
  conflictKey: string;
  mutation: SyncMutationPayload;
  serverRecord: SyncConflictPayload['registro_servidor'];
  message: string;
  detectedAt: string;
}

function buildKey(entity: string, id: string): string {
  return `${entity}:${id}`;
}

export function listSyncConflicts(): SyncConflictItem[] {
  if (typeof window === 'undefined' || !window.localStorage) return [];
  try {
    const raw = window.localStorage.getItem(SYNC_CONFLICTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as SyncConflictItem[]) : [];
  } catch {
    return [];
  }
}

function saveConflicts(items: SyncConflictItem[]): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  try {
    window.localStorage.setItem(SYNC_CONFLICTS_STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* localStorage lleno o bloqueado */
  }
}

export function enqueueSyncConflict(
  mutation: SyncMutationPayload,
  conflicto: SyncConflictPayload,
): SyncConflictItem {
  const conflictKey = buildKey(mutation.entity, mutation.id);
  const item: SyncConflictItem = {
    conflictKey,
    mutation,
    serverRecord: conflicto.registro_servidor,
    message: conflicto.error || 'El registro fue modificado en el servidor.',
    detectedAt: new Date().toISOString(),
  };
  const next = listSyncConflicts().filter((c) => c.conflictKey !== conflictKey);
  next.push(item);
  saveConflicts(next);
  return item;
}

export function removeSyncConflict(conflictKey: string): void {
  const next = listSyncConflicts().filter((c) => c.conflictKey !== conflictKey);
  saveConflicts(next);
}

export function clearSyncConflicts(): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  try {
    window.localStorage.removeItem(SYNC_CONFLICTS_STORAGE_KEY);
  } catch {
    /* noop */
  }
}

/**
 * Reintenta un conflicto enviando los mismos `cambios` locales con el nuevo
 * cursor `serverRecord.fecha_actualizacion`. Si tiene éxito lo retira de la cola;
 * si vuelve a responder 409 actualiza la copia `serverRecord` en cola.
 */
export async function retrySyncConflictWithServerCursor(
  item: SyncConflictItem,
  idempotencyKey?: string,
): Promise<SyncPushResult> {
  const updatedPayload: SyncMutationPayload = {
    ...item.mutation,
    expected_fecha_actualizacion: item.serverRecord.fecha_actualizacion,
  };
  const result = await pushOptimisticUpdate(updatedPayload, idempotencyKey);
  if (result.ok) {
    removeSyncConflict(item.conflictKey);
  } else {
    enqueueSyncConflict(updatedPayload, result.conflicto);
  }
  return result;
}
