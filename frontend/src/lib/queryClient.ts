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
 * Reintento de mutaciones (sin outbox completo): solo errores de red puros y
 * hasta MUTATION_MAX_RETRIES veces. Es seguro porque la petición nunca llegó
 * al servidor; para POST de pagos además viaja `Idempotency-Key`
 * (ver `lib/idempotency.ts` + PR #86), que deduplica en backend.
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
      retry: mutationRetry,
      retryDelay: retryBackoffDelay,
      networkMode: 'online',
    },
  },
});
