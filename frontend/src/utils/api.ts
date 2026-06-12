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

/**
 * Convierte el `Error` que lanzan los helpers de `services/api` (cuyo message
 * es el body JSON del backend serializado) en un texto legible para la UI.
 * Soporta los formatos de DRF: `["msg"]`, `{"detail": "..."}` y
 * `{"campo": ["msg", ...]}`.
 */
/**
 * Status HTTP que `services/api.buildError` adjunta al Error, o undefined si
 * el error no proviene de una respuesta HTTP (p. ej. fallo de red o de código).
 */
export function statusDeError(err: unknown): number | undefined {
  if (err instanceof Error) {
    const status = (err as Error & { status?: unknown }).status;
    if (typeof status === 'number') return status;
  }
  return undefined;
}

export function mensajeDeError(err: unknown, fallback = 'Error inesperado'): string {
  if (!(err instanceof Error) || !err.message) return fallback;
  try {
    const parsed: unknown = JSON.parse(err.message);
    if (Array.isArray(parsed)) return parsed.map(String).join(' · ') || fallback;
    if (parsed && typeof parsed === 'object') {
      const partes: string[] = [];
      for (const [campo, valor] of Object.entries(parsed as Record<string, unknown>)) {
        const texto = Array.isArray(valor) ? valor.map(String).join(' ') : String(valor);
        const esGenerico = ['detail', 'error', 'non_field_errors'].includes(campo);
        partes.push(esGenerico ? texto : `${campo}: ${texto}`);
      }
      return partes.join(' · ') || fallback;
    }
    return String(parsed) || fallback;
  } catch {
    return err.message;
  }
}
