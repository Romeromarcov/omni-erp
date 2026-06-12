/**
 * Claves de idempotencia para mutaciones de pago (PR #86, backend
 * `apps/core/idempotency.py`): el backend deduplica POSTs que llegan con el
 * mismo header `Idempotency-Key`.
 *
 * Punto de extensión offline Nivel 1: la clave se genera UNA vez por
 * operación lógica (al construir el payload, no por intento HTTP), de modo
 * que los reintentos automáticos de TanStack Query (`mutationRetry` en
 * `lib/queryClient.ts`) reutilizan la misma clave y no pueden duplicar el
 * pago aunque el primer intento sí hubiera llegado al servidor.
 */
export const IDEMPOTENCY_HEADER = 'Idempotency-Key';

export function newIdempotencyKey(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') {
    return c.randomUUID();
  }
  // Fallback (entornos sin crypto.randomUUID, p. ej. WebViews viejos).
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}
