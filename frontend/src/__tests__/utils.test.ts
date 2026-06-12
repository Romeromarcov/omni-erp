import { describe, it, expect } from 'vitest';
import { toList, toCount, statusDeError } from '../utils/api';
import type { HttpError } from '../services/api';

describe('toList', () => {
  it('returns the array as-is when given a plain array', () => {
    const input = [{ id: 1 }, { id: 2 }];
    expect(toList(input)).toEqual(input);
  });

  it('returns results from a paginated response', () => {
    const input = { results: [{ id: 1 }], count: 1, next: null, previous: null };
    expect(toList(input)).toEqual([{ id: 1 }]);
  });

  it('returns empty array for unexpected input', () => {
    // Cast to bypass TypeScript — simulates runtime edge case
    expect(toList({} as never)).toEqual([]);
  });
});

describe('toCount', () => {
  it('returns the length of a plain array', () => {
    expect(toCount([1, 2, 3])).toBe(3);
  });

  it('returns count from a paginated response', () => {
    const input = { results: [], count: 42, next: null, previous: null };
    expect(toCount(input)).toBe(42);
  });

  it('returns 0 for an empty object', () => {
    expect(toCount({} as never)).toBe(0);
  });
});

describe('statusDeError', () => {
  it('devuelve el status adjuntado por services/api.buildError', () => {
    const err: HttpError = new Error('{"error":"falta mapeo NOMINA"}');
    err.status = 422;
    expect(statusDeError(err)).toBe(422);
  });

  it('devuelve undefined para errores sin status (red, código)', () => {
    expect(statusDeError(new Error('network down'))).toBeUndefined();
    expect(statusDeError('no soy un Error')).toBeUndefined();
    expect(statusDeError(undefined)).toBeUndefined();
  });

  it('ignora un status que no sea numérico', () => {
    const err = new Error('x') as Error & { status?: unknown };
    err.status = 'malo';
    expect(statusDeError(err)).toBeUndefined();
  });
});
