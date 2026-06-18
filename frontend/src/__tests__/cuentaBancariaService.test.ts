/**
 * Cobertura del servicio de cuentas bancarias (Q1: cobertura frontend).
 * Verifica construcción de endpoints, inyección de `empresa` y query params.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(() => Promise.resolve({ results: [] })),
  post: vi.fn(() => Promise.resolve({})),
  put: vi.fn(() => Promise.resolve({})),
}));

import { get, post, put } from '../services/api';
import {
  getMovimientosCuentaBancaria,
  getCuentasBancarias,
  updateCuentaBancaria,
  createCuentaBancaria,
  getCuentaBancariaDetail,
} from '../services/cuentaBancariaService';

describe('cuentaBancariaService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getCuentasBancarias inyecta empresa como query param', async () => {
    await getCuentasBancarias('emp-1', { activo: 'true' });
    const url = vi.mocked(get).mock.calls[0][0] as string;
    const qs = new URL(url, 'http://x').searchParams;
    expect(qs.get('empresa')).toBe('emp-1');
    expect(qs.get('activo')).toBe('true');
    expect(url.startsWith('/finanzas/cuentas-bancarias-empresa/?')).toBe(true);
  });

  it('getCuentasBancarias sin filtros no añade "?" colgante de más', async () => {
    await getCuentasBancarias('emp-1');
    const url = vi.mocked(get).mock.calls[0][0] as string;
    expect(url).toContain('empresa=emp-1');
  });

  it('getMovimientosCuentaBancaria arma el endpoint anidado con filtros', async () => {
    await getMovimientosCuentaBancaria('cb-7', { desde: '2026-01-01' });
    const url = vi.mocked(get).mock.calls[0][0] as string;
    expect(url).toContain('/finanzas/cuentas-bancarias-empresa/cb-7/movimientos-cuenta-bancaria/');
    expect(url).toContain('desde=2026-01-01');
  });

  it('getMovimientosCuentaBancaria sin filtros omite el "?"', async () => {
    await getMovimientosCuentaBancaria('cb-7');
    const url = vi.mocked(get).mock.calls[0][0] as string;
    expect(url.endsWith('/movimientos-cuenta-bancaria/')).toBe(true);
  });

  it('createCuentaBancaria mapea empresa en el payload', async () => {
    await createCuentaBancaria('emp-1', { numero: '0102' });
    expect(post).toHaveBeenCalledWith('/finanzas/cuentas-bancarias-empresa/', {
      numero: '0102', empresa: 'emp-1',
    });
  });

  it('update/detail apuntan al recurso por id', async () => {
    await updateCuentaBancaria('cb-7', { alias: 'X' });
    expect(put).toHaveBeenCalledWith('/finanzas/cuentas-bancarias-empresa/cb-7/', { alias: 'X' });
    await getCuentaBancariaDetail('cb-7');
    expect(get).toHaveBeenCalledWith('/finanzas/cuentas-bancarias-empresa/cb-7/');
  });
});
