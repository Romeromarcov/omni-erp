import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  // El hook usa getAccessToken() para habilitar la query de sesión activa.
  getAccessToken: vi.fn(() => 'test-token'),
}));

vi.mock('../services/sesionService', () => ({
  getSesionActiva: vi.fn().mockResolvedValue(null),
}));

import { get } from '../services/api';
import { useModalPagoData } from '../components/Pedidos/useModalPagoData';

const mockGet = get as unknown as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

// Implementación de `get` por URL para enrutar cada query a su respuesta.
function routeGet(routes: Record<string, unknown>, fallback: unknown = { results: [] }) {
  return (url: string) => {
    for (const [needle, value] of Object.entries(routes)) {
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
  localStorage.clear();
});

afterEach(() => {
  cleanup();
});

describe('useModalPagoData — tasa BCV', () => {
  it('bloquea el submit (tasaBCVNoDisponible) y expone el error cuando la tasa BCV falla', async () => {
    mockGet.mockImplementation(
      routeGet({
        'tasa-oficial-bcv': new Error('BCV caído'),
      })
    );

    const { result } = renderHook(() => useModalPagoData({ empresaId: 'emp-1' }), { wrapper });

    await waitFor(() => expect(result.current.tasaBCVError).not.toBeNull());
    expect(result.current.tasaBCVError?.message).toBe('BCV caído');
    expect(result.current.tasaBCVNoDisponible).toBe(true);
    // Cae al valor por defecto seguro de 1 cuando no hay tasa.
    expect(result.current.tasaBCV).toBe(1);
  });

  it('expone la tasa y no bloquea el submit cuando la carga es exitosa', async () => {
    mockGet.mockImplementation(
      routeGet({
        'tasa-oficial-bcv': { valor_tasa: '36.50' },
        'metodos-pago': { results: [{ id_metodo_pago: 'm1', nombre_metodo: 'Efectivo' }] },
        'monedas': { results: [{ id_moneda: 'usd', codigo_iso: 'USD' }] },
      })
    );

    const { result } = renderHook(() => useModalPagoData({ empresaId: 'emp-1' }), { wrapper });

    await waitFor(() => expect(result.current.tasaBCVLoading).toBe(false));
    expect(result.current.tasaBCV).toBe(36.5);
    expect(result.current.tasaBCVError).toBeNull();
    expect(result.current.tasaBCVNoDisponible).toBe(false);
  });

  it('carga métodos y monedas exitosamente', async () => {
    mockGet.mockImplementation(
      routeGet({
        'tasa-oficial-bcv': { valor_tasa: '36.50' },
        'metodos-pago-empresa-activas': { results: [] },
        'metodos-pago': { results: [{ id_metodo_pago: 'm1', nombre_metodo: 'Efectivo' }] },
        'monedas-empresa-activas': { results: [] },
        'monedas': { results: [{ id_moneda: 'usd', codigo_iso: 'USD' }] },
      })
    );

    const { result } = renderHook(() => useModalPagoData({ empresaId: 'emp-1' }), { wrapper });

    await waitFor(() => expect(result.current.metodos.length).toBe(1));
    expect(result.current.metodos[0].id_metodo_pago).toBe('m1');
    await waitFor(() => expect(result.current.monedas.length).toBe(1));
    expect(result.current.monedas[0].codigo_iso).toBe('USD');
  });
});
