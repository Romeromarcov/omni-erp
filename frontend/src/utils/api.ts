/**
 * Utilidades compartidas para normalizar respuestas de la API.
 * La API puede devolver listas directas o paginadas { results, count }.
 */

/** Respuesta paginada estándar de DRF */
export interface PaginatedResponse<T> {
  results: T[];
  count?: number;
  next?: string | null;
  previous?: string | null;
}

/** Normaliza una respuesta de DRF (lista directa o paginada) a un array. */
export function toList<T>(raw: unknown): T[] {
  if (Array.isArray(raw)) return raw as T[];
  if (raw && typeof raw === 'object' && Array.isArray((raw as PaginatedResponse<T>).results)) {
    return (raw as PaginatedResponse<T>).results;
  }
  return [];
}

/** Extrae el count de una respuesta paginada (0 para listas directas). */
export function toCount<T = unknown>(raw: unknown): number {
  if (Array.isArray(raw)) return (raw as T[]).length;
  if (raw && typeof raw === 'object' && typeof (raw as PaginatedResponse<T>).count === 'number') {
    return (raw as PaginatedResponse<T>).count ?? 0;
  }
  return 0;
}
