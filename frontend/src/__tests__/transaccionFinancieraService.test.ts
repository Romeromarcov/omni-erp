/**
 * Cobertura del servicio de transacciones financieras (Q1: cobertura frontend).
 * Verifica el mapeo de filtros a query params (omite vacíos/null/undefined), la
 * construcción de URLs y las acciones que abren ventana (export/print).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(() => Promise.resolve({ results: [] })),
  post: vi.fn(() => Promise.resolve({})),
  put: vi.fn(() => Promise.resolve({})),
}));

import { get, post, put } from '../services/api';
import {
  getTransaccionesFinancieras,
  exportTransaccionesFinancieras,
  getTransaccionFinancieraDetail,
  updateTransaccionFinanciera,
  printTransaccionFinanciera,
  createIngreso,
  createEgreso,
} from '../services/transaccionFinancieraService';

describe('transaccionFinancieraService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('mapea filtros a query params y omite vacíos/null/undefined', async () => {
    await getTransaccionesFinancieras('emp-1', {
      tipo: 'INGRESO',
      vacio: '',
      nulo: null,
      indef: undefined,
      monto: 100,
    });
    const url = vi.mocked(get).mock.calls[0][0] as string;
    const qs = new URL(url, 'http://x').searchParams;
    expect(qs.get('id_empresa')).toBe('emp-1');
    expect(qs.get('tipo')).toBe('INGRESO');
    expect(qs.get('monto')).toBe('100');
    expect(qs.has('vacio')).toBe(false);
    expect(qs.has('nulo')).toBe(false);
    expect(qs.has('indef')).toBe(false);
  });

  it('omite id_empresa cuando es undefined', async () => {
    await getTransaccionesFinancieras(undefined, {});
    const url = vi.mocked(get).mock.calls[0][0] as string;
    expect(url).not.toContain('id_empresa');
  });

  it('export abre la ventana de exportación con los filtros', async () => {
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null);
    await exportTransaccionesFinancieras('emp-1', { tipo: 'EGRESO' });
    expect(openSpy).toHaveBeenCalledTimes(1);
    const url = openSpy.mock.calls[0][0] as string;
    expect(url).toContain('/finanzas/transacciones-financieras/export/');
    expect(url).toContain('tipo=EGRESO');
    openSpy.mockRestore();
  });

  it('detail/update apuntan al recurso por id', async () => {
    await getTransaccionFinancieraDetail('t-9');
    expect(get).toHaveBeenCalledWith('/finanzas/transacciones-financieras/t-9/');
    await updateTransaccionFinanciera('t-9', { glosa: 'x' });
    expect(put).toHaveBeenCalledWith('/finanzas/transacciones-financieras/t-9/', { glosa: 'x' });
  });

  it('print abre la ventana de impresión', async () => {
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null);
    await printTransaccionFinanciera('t-1');
    expect(openSpy).toHaveBeenCalledWith('/finanzas/transacciones-financieras/t-1/print/', '_blank');
    openSpy.mockRestore();
  });

  it('createIngreso/createEgreso postean al endpoint con id_empresa en query', async () => {
    await createIngreso('emp-1', { monto: '5' });
    expect(post).toHaveBeenCalledWith(
      '/finanzas/transacciones-financieras/ingreso/?id_empresa=emp-1', { monto: '5' },
    );
    await createEgreso('emp-1', { monto: '7' });
    expect(post).toHaveBeenCalledWith(
      '/finanzas/transacciones-financieras/egreso/?id_empresa=emp-1', { monto: '7' },
    );
  });
});
