import { QueryClient } from '@tanstack/react-query';

/**
 * Offline Nivel 1 (ADR-001 / Plan Maestro §5.2-ter Fase 2).
 *
 * Detección de error de red: `fetch` rechaza con `TypeError` cuando la
 * conexión falla (DNS, sin red, conexión cortada). Los errores HTTP
 * (4xx/5xx) los lanza `services/api.ts` como `Error` con cuerpo JSON —
 * esos NO se reintentan en mutaciones porque el servidor ya recibió la
 * petición.
 */
export function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError;
}

/** Máximo de reintentos automáticos para mutaciones con error de red. */
export const MUTATION_MAX_RETRIES = 3;

/**
 * Reintento de mutaciones — SOLO opt-in por mutación, nunca global.
 *
 * Un `TypeError` de red NO garantiza que la petición no llegó al servidor:
 * la conexión puede cortarse después de enviar el POST y antes de recibir la
 * respuesta. Reintentar automáticamente una mutación sin idempotencia en ese
 * caso DUPLICA la operación (pago, abono, pedido). Por eso el default global
 * de mutaciones es retry: false; este helper se pasa explícitamente en el
 * `useMutation` de operaciones que adjuntan una `Idempotency-Key` ESTABLE
 * (generada junto con las variables de la mutación — ver `lib/idempotency.ts`
 * + PR #86), donde el backend deduplica y el reintento es seguro.
 */
export function mutationRetry(failureCount: number, error: unknown): boolean {
  return isNetworkError(error) && failureCount < MUTATION_MAX_RETRIES;
}

/** Backoff exponencial: 1s, 2s, 4s… con techo de 30s. */
export function retryBackoffDelay(attemptIndex: number): number {
  return Math.min(1000 * 2 ** attemptIndex, 30_000);
}

/**
 * Instancia global de QueryClient.
 * Configuración conservadora para un ERP:
 *  - staleTime 30s: los datos de lista se consideran frescos por 30 segundos.
 *  - queries.retry 1: un solo reintento; los 401 los maneja api.ts.
 *  - refetchOnWindowFocus false: evita requests inesperados al volver al tab.
 *  - networkMode 'online': sin red, las queries quedan en pausa (sirviendo el
 *    caché si existe) y las mutaciones quedan `isPaused` hasta que vuelva la
 *    conexión — entonces se reanudan solas y el retry/backoff completa el
 *    envío (DoD de la fase: "los reintentos completan al volver la red").
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      retryDelay: retryBackoffDelay,
      refetchOnWindowFocus: false,
      networkMode: 'online',
    },
    mutations: {
      // Sin retry automático global: una mutación sin Idempotency-Key podría
      // duplicarse si la red se corta tras enviar el POST. El caso offline
      // sigue cubierto por networkMode 'online' (la mutación queda isPaused
      // SIN haberse enviado y se reanuda sola al volver la conexión). Las
      // mutaciones idempotentes optan al retry pasando `mutationRetry`.
      retry: false,
      retryDelay: retryBackoffDelay,
      networkMode: 'online',
    },
  },
});
