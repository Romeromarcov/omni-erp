/**
 * Offline Nivel 1 — config de retry/backoff del QueryClient y claves de
 * idempotencia para mutaciones de pago.
 */
import { describe, it, expect } from 'vitest';
import {
  queryClient,
  isNetworkError,
  mutationRetry,
  retryBackoffDelay,
  MUTATION_MAX_RETRIES,
} from '../lib/queryClient';
import { newIdempotencyKey, IDEMPOTENCY_HEADER } from '../lib/idempotency';

describe('isNetworkError', () => {
  it('un TypeError de fetch es error de red', () => {
    expect(isNetworkError(new TypeError('Failed to fetch'))).toBe(true);
  });

  it('un error HTTP (Error con cuerpo JSON de api.ts) NO es error de red', () => {
    expect(isNetworkError(new Error('{"error":"Saldo insuficiente"}'))).toBe(false);
    expect(isNetworkError(undefined)).toBe(false);
  });
});

describe('mutationRetry', () => {
  const netError = new TypeError('Failed to fetch');

  it('reintenta errores de red hasta el máximo', () => {
    expect(mutationRetry(0, netError)).toBe(true);
    expect(mutationRetry(MUTATION_MAX_RETRIES - 1, netError)).toBe(true);
    expect(mutationRetry(MUTATION_MAX_RETRIES, netError)).toBe(false);
  });

  it('nunca reintenta errores HTTP (el servidor ya recibió la petición)', () => {
    expect(mutationRetry(0, new Error('{"error":"422"}'))).toBe(false);
  });
});

describe('retryBackoffDelay', () => {
  it('crece exponencialmente con techo de 30s', () => {
    expect(retryBackoffDelay(0)).toBe(1000);
    expect(retryBackoffDelay(1)).toBe(2000);
    expect(retryBackoffDelay(2)).toBe(4000);
    expect(retryBackoffDelay(10)).toBe(30_000);
  });
});

describe('queryClient (defaults offline Nivel 1)', () => {
  it('mutaciones: networkMode online, SIN retry global (anti-duplicados)', () => {
    // Un TypeError de red no garantiza que el POST no llegó al servidor:
    // reintentar una mutación sin Idempotency-Key duplicaría la operación.
    // El retry es opt-in por mutación (mutationRetry + key estable).
    const defaults = queryClient.getDefaultOptions();
    expect(defaults.mutations?.networkMode).toBe('online');
    expect(defaults.mutations?.retry).toBe(false);
    expect(defaults.mutations?.retryDelay).toBe(retryBackoffDelay);
  });

  it('queries: networkMode online (pausa sin red, sirve caché) y backoff', () => {
    const defaults = queryClient.getDefaultOptions();
    expect(defaults.queries?.networkMode).toBe('online');
    expect(defaults.queries?.retry).toBe(1);
    expect(defaults.queries?.retryDelay).toBe(retryBackoffDelay);
  });
});

describe('idempotencia (PR #86)', () => {
  it('expone el nombre de header que espera el backend', () => {
    expect(IDEMPOTENCY_HEADER).toBe('Idempotency-Key');
  });

  it('genera claves únicas con formato UUID', () => {
    const a = newIdempotencyKey();
    const b = newIdempotencyKey();
    expect(a).not.toBe(b);
    expect(a).toMatch(/^[0-9a-f-]{36}$/i);
  });
});
