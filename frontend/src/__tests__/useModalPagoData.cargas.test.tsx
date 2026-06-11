import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  getAccessToken: vi.fn(() => 'test-token'),
}));

vi.mock('../services/sesionService', () => ({
  getSesionActiva: vi.fn(),
}));

import { get } from '../services/api';
import { getSesionActiva } from '../services/sesionService';
import { useModalPagoData } from '../components/Pedidos/useModalPagoData';

const mockGet = get as unknown as ReturnType<typeof vi.fn>;
const mockGetSesionActiva = getSesionActiva as unknown as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

// Enruta cada GET por substring de la URL. El orden importa: gana el primer match.
function routeGet(routes: Array<[string, unknown]>, fallback: unknown = { results: [] }) {
  return (url: string) => {
    for (const [needle, value] of routes) {
      if (url.includes(needle)) {
        if (value instanceof Error) return Promise.reject(value);
        return Promise.resolve(value);
      }
    }
    return Promise.resolve(fallback);
  };
}

beforeEach(() => {
  mockGet.mockReset();
  mockGetSesionActiva.mockReset();
  mockGetSesionActiva.mockResolvedValue(null);
});

afterEach(() => cleanup());

describe('useModalPagoData — métodos y monedas filtrados por empresa', () => {
  it('filtra los métodos de pago desactivados para la empresa', async () => {
    mockGet.mockImplementation(routeGet([
      ['tasa-oficial-bcv', { valor_tasa: '36.50' }],
      ['metodos-pago-empresa-activas', { results: [
        { empresa: 'emp-1', metodo_pago: 'm1', activa: false },
        { empresa: 'emp-1', metodo_pago: 'm2', activa: true },
      ] }],
      ['metodos-pago', { results: [
        { id_metodo_pago: 'm1', nombre_metodo: 'Efectivo', tipo_metodo: 'efectivo' },
        { id_metodo_pago: 'm2', nombre_metodo: 'Zelle', tipo_metodo: 'transferencia' },
        { id_metodo_pago: 'm3', nombre_metodo: 'Cripto', tipo_metodo: 'otro' },
      ] }],
    ]));

    const { result } = renderHook(() => useModalPagoData({ empresaId: 'emp-1' }), { wrapper });

    await waitFor(() => expect(result.current.metodos.length).toBe(2));
    // m1 desactivado se filtra; m3 sin registro de activación queda activo por defecto.
    expect(result.current.metodos.map(m => m.id_metodo_pago)).toEqual(['m2', 'm3']);
  });

  it('filtra las monedas desactivadas para la empresa', async () => {
    mockGet.mockImplementation(routeGet([
      ['tasa-oficial-bcv', { valor_tasa: '36.50' }],
      ['monedas-empresa-activas', { results: [
        { empresa: 'emp-1', moneda: 'ves', activa: false },
        { empresa: 'emp-1', moneda: 'usd', activa: true },
      ] }],
      ['monedas', { results: [
        { id_moneda: 'usd', codigo_iso: 'USD', nombre: 'Dólar' },
        { id_moneda: 'ves', codigo_iso: 'VES', nombre: 'Bolívar' },
      ] }],
    ]));

    const { result } = renderHook(() => useModalPagoData({ empresaId: 'emp-1' }), { wrapper });

    await waitFor(() => expect(result.current.monedas.length).toBe(1));
    expect(result.current.monedas[0].codigo_iso).toBe('USD');
  });
});

describe('useModalPagoData — parámetros de tolerancia', () => {
  it('lee la tolerancia positiva y el flag de negativas de los parámetros del sistema', async () => {
    mockGet.mockImplementation(routeGet([
      ['tasa-oficial-bcv', { valor_tasa: '36.50' }],
      ['parametros-sistema', { results: [
        { id_parametro: 'p1', codigo_parametro: 'TOLERANCIA_DIFERENCIA_POSITIVA_PAGOS', valor_parametro: '1.25', tipo_dato: 'decimal' },
        { id_parametro: 'p2', codigo_parametro: 'PERMITIR_DIFERENCIAS_NEGATIVAS_PAGOS', valor_parametro: 'False', tipo_dato: 'bool' },
      ] }],
    ]));

    const { result } = renderHook(() => useModalPagoData({ empresaId: 'emp-1' }), { wrapper });

    await waitFor(() => expect(result.current.toleranciaPositiva).toBe(1.25));
    expect(result.current.permitirNegativas).toBe(false);
  });

  it('cae a los defaults seguros (0.5 / true) si los parámetros no existen o no parsean', async () => {
    mockGet.mockImplementation(routeGet([
      ['tasa-oficial-bcv', { valor_tasa: '36.50' }],
      ['parametros-sistema', { results: [
        { id_parametro: 'p1', codigo_parametro: 'TOLERANCIA_DIFERENCIA_POSITIVA_PAGOS', valor_parametro: 'no-numero', tipo_dato: 'decimal' },
      ] }],
    ]));

    const { result } = renderHook(() => useModalPagoData({ empresaId: 'emp-1' }), { wrapper });

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    await waitFor(() => expect(result.current.toleranciaPositiva).toBe(0.5));
    expect(result.current.permitirNegativas).toBe(true);
  });
});

describe('useModalPagoData — cajas, cuentas y datáfonos vía sesión activa', () => {
  const SESION = {
    id_sesion: 's1',
    caja_fisica_principal: { id_caja: 'cf-1' },
  };

  it('carga las cajas virtuales de la caja física de la sesión y normaliza moneda objeto/string', async () => {
    mockGetSesionActiva.mockResolvedValue(SESION);
    mockGet.mockImplementation(routeGet([
      ['tasa-oficial-bcv', { valor_tasa: '36.50' }],
      ['finanzas/cajas/', { results: [
        { id_caja: 'cv-1', nombre: 'Caja USD', moneda: { codigo_iso: 'USD' }, moneda_codigo_iso: 'USD', activa: true },
        { id_caja: 'cv-2', nombre: 'Caja VES', moneda: 'ves', moneda_codigo_iso: 'VES', activa: true, caja_fisica: 'cf-1' },
      ] }],
    ]));

    const { result } = renderHook(() => useModalPagoData({ empresaId: 'emp-1' }), { wrapper });

    await waitFor(() => expect(result.current.cajas.length).toBe(2));
    expect(result.current.cajaFisicaActual).toEqual({ id_caja: 'cf-1' });
    // moneda objeto → usa codigo_iso y deja id_moneda vacío
    expect(result.current.cajas[0]).toMatchObject({ id_caja: 'cv-1', moneda: 'USD', id_moneda: '' });
    // moneda string → la usa como id_moneda
    expect(result.current.cajas[1]).toMatchObject({ id_caja: 'cv-2', moneda: 'ves', id_moneda: 'ves' });
  });

  it('carga cuentas bancarias de la empresa', async () => {
    mockGet.mockImplementation(routeGet([
      ['tasa-oficial-bcv', { valor_tasa: '36.50' }],
      ['cuentas-bancarias', { results: [
        { id_cuenta_bancaria: 'cb-1', nombre_cuenta: 'Cta', numero_cuenta: '0102', id_moneda: 'ves', id_banco: 'b1', nombre_banco: 'BNC' },
      ] }],
    ]));

    const { result } = renderHook(() => useModalPagoData({ empresaId: 'emp-1' }), { wrapper });

    await waitFor(() => expect(result.current.cuentasBancarias.length).toBe(1));
    expect(result.current.cuentasBancarias[0].id_cuenta_bancaria).toBe('cb-1');
  });

  it('normaliza los datáfonos cuando llegan como {results}, {data} o array', async () => {
    mockGetSesionActiva.mockResolvedValue(SESION);
    const datafono = { id_datafono: 'dt-1', nombre: 'Punto 1', id_moneda: 'ves', id_cuenta_bancaria: 'cb-1' };

    for (const shape of [{ results: [datafono] }, { data: [datafono] }, [datafono]]) {
      cleanup();
      mockGet.mockImplementation(routeGet([
        ['tasa-oficial-bcv', { valor_tasa: '36.50' }],
        ['datafonos', shape],
      ]));

      const { result } = renderHook(() => useModalPagoData({ empresaId: 'emp-1' }), { wrapper });
      await waitFor(() => expect(result.current.datafonos.length).toBe(1));
      expect(result.current.datafonos[0].id_datafono).toBe('dt-1');
    }
  });

  it('devuelve datáfonos vacíos ante una respuesta con forma inesperada', async () => {
    mockGetSesionActiva.mockResolvedValue(SESION);
    mockGet.mockImplementation(routeGet([
      ['tasa-oficial-bcv', { valor_tasa: '36.50' }],
      ['datafonos', { inesperado: true }],
    ]));

    const { result } = renderHook(() => useModalPagoData({ empresaId: 'emp-1' }), { wrapper });
    await waitFor(() => expect(mockGet.mock.calls.some(c => String(c[0]).includes('datafonos'))).toBe(true));
    await waitFor(() => expect(result.current.datafonos).toEqual([]));
  });
});

describe('useModalPagoData — notas de crédito', () => {
  it('consulta notas de crédito del cliente cuando hay idCliente', async () => {
    mockGet.mockImplementation(routeGet([
      ['tasa-oficial-bcv', { valor_tasa: '36.50' }],
      ['notas-credito-cliente', { results: [
        { id_nota_credito: 'nc-1', numero_nota: 'NC-1', monto_disponible: 5, id_moneda: 'usd', fecha_emision: '2026-01-01' },
      ] }],
    ]));

    const { result } = renderHook(
      () => useModalPagoData({ empresaId: 'emp-1', idCliente: 'cli-1' }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.notasCredito.length).toBe(1));
    const url = mockGet.mock.calls.map(c => String(c[0])).find(u => u.includes('notas-credito-cliente'));
    expect(url).toContain('id_cliente=cli-1');
    expect(url).toContain('id_empresa=emp-1');
  });

  it('consulta notas de crédito del proveedor cuando hay idProveedor (sin cliente)', async () => {
    mockGet.mockImplementation(routeGet([
      ['tasa-oficial-bcv', { valor_tasa: '36.50' }],
      ['notas-credito-proveedor', { results: [] }],
    ]));

    renderHook(
      () => useModalPagoData({ empresaId: 'emp-1', idProveedor: 'prov-1' }),
      { wrapper },
    );

    await waitFor(() => {
      const url = mockGet.mock.calls.map(c => String(c[0])).find(u => u.includes('notas-credito-proveedor'));
      expect(url).toContain('id_proveedor=prov-1');
    });
  });
});
