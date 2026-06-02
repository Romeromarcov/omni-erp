import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
}));

import { get } from '../services/api';
import { useCarteraDashboard, useTasaHoy, useAcuerdos } from '../hooks/useCxC';

const mockGet = get as unknown as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  mockGet.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('useCarteraDashboard', () => {
  it('expone data/loading/error/refresh y carga el dashboard', async () => {
    mockGet.mockResolvedValueOnce({ total_pendiente: '100.00', buckets: {} });
    const { result } = renderHook(() => useCarteraDashboard(), { wrapper });

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(mockGet).toHaveBeenCalledWith('/cobranza/cartera/dashboard/');
    expect(result.current.data).toEqual({ total_pendiente: '100.00', buckets: {} });
    expect(result.current.error).toBeNull();
    expect(typeof result.current.refresh).toBe('function');
  });

  it('expone error.message cuando la query falla', async () => {
    mockGet.mockRejectedValueOnce(new Error('fallo cartera'));
    const { result } = renderHook(() => useCarteraDashboard(), { wrapper });

    await waitFor(() => expect(result.current.error).toBe('fallo cartera'));
    expect(result.current.data).toBeNull();
  });
});

describe('useTasaHoy', () => {
  it('devuelve la tasa cuyo fecha_tasa coincide con hoy', async () => {
    const hoy = new Date().toISOString().split('T')[0];
    mockGet.mockResolvedValueOnce({
      results: [{ valor_tasa: '36.50', tipo_tasa: 'OFICIAL_BCV', fecha_tasa: hoy }],
    });
    const { result } = renderHook(() => useTasaHoy(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.tasa).toBe('36.50');
  });

  it('devuelve null si no hay tasa para hoy', async () => {
    mockGet.mockResolvedValueOnce({
      results: [{ valor_tasa: '36.50', tipo_tasa: 'OFICIAL_BCV', fecha_tasa: '2000-01-01' }],
    });
    const { result } = renderHook(() => useTasaHoy(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.tasa).toBeNull();
  });
});

describe('useAcuerdos', () => {
  it('usa el endpoint sin filtro cuando no hay estado', async () => {
    mockGet.mockResolvedValueOnce({ results: [] });
    const { result } = renderHook(() => useAcuerdos(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockGet).toHaveBeenCalledWith('/cobranza/acuerdos/');
    expect(result.current.data).toEqual({ results: [] });
  });

  it('incluye el estado en el endpoint cuando se pasa', async () => {
    mockGet.mockResolvedValueOnce({ results: [] });
    const { result } = renderHook(() => useAcuerdos('vigente'), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockGet).toHaveBeenCalledWith('/cobranza/acuerdos/?estado=vigente');
  });
});
