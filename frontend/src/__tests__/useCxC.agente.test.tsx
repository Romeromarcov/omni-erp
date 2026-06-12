import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  streamSSE: vi.fn(),
}));

import { streamSSE } from '../services/api';
import { useAgenteStream, useInvalidateCxC } from '../hooks/useCxC';
import { cxcKeys } from '../lib/queryKeys';

const mockStreamSSE = streamSSE as unknown as ReturnType<typeof vi.fn>;

type SSECallback = (event: Record<string, unknown>) => void;

let queryClient: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mockStreamSSE.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('useAgenteStream', () => {
  it('acumula el texto de los eventos SSE y termina con streaming=false', async () => {
    mockStreamSSE.mockImplementation(async (_url: string, onEvent: SSECallback) => {
      onEvent({ text: 'Hola ' });
      onEvent({ text: 'mundo' });
    });

    const { result } = renderHook(() => useAgenteStream(), { wrapper });
    expect(result.current.streaming).toBe(false);

    await act(async () => {
      await result.current.iniciar('analizar_cartera');
    });

    expect(result.current.output).toBe('Hola mundo');
    expect(result.current.error).toBeNull();
    expect(result.current.streaming).toBe(false);
  });

  it('envía la acción y los params en el body del POST', async () => {
    mockStreamSSE.mockResolvedValue(undefined);
    const { result } = renderHook(() => useAgenteStream(), { wrapper });

    await act(async () => {
      await result.current.iniciar('gestionar_cliente', { id_cliente: 'cli-1' });
    });

    expect(mockStreamSSE).toHaveBeenCalledWith(
      '/cobranza/agente/',
      expect.any(Function),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ accion: 'gestionar_cliente', id_cliente: 'cli-1' }),
      }),
    );
  });

  it('expone el error recibido en un evento SSE de error', async () => {
    mockStreamSSE.mockImplementation(async (_url: string, onEvent: SSECallback) => {
      onEvent({ error: 'cuota excedida' });
    });

    const { result } = renderHook(() => useAgenteStream(), { wrapper });
    await act(async () => {
      await result.current.iniciar('analizar_cartera');
    });

    expect(result.current.error).toBe('cuota excedida');
  });

  it('captura excepciones del stream y deja streaming=false', async () => {
    mockStreamSSE.mockRejectedValue(new Error('red caída'));
    const { result } = renderHook(() => useAgenteStream(), { wrapper });

    await act(async () => {
      await result.current.iniciar('analizar_cartera');
    });

    await waitFor(() => expect(result.current.error).toBe('red caída'));
    expect(result.current.streaming).toBe(false);
  });

  it('limpiar resetea output y error', async () => {
    mockStreamSSE.mockImplementation(async (_url: string, onEvent: SSECallback) => {
      onEvent({ text: 'algo' });
      onEvent({ error: 'fallo' });
    });

    const { result } = renderHook(() => useAgenteStream(), { wrapper });
    await act(async () => {
      await result.current.iniciar('analizar_cartera');
    });
    expect(result.current.output).toBe('algo');

    act(() => result.current.limpiar());
    expect(result.current.output).toBe('');
    expect(result.current.error).toBeNull();
  });
});

describe('useInvalidateCxC', () => {
  it('invalida cartera, acuerdos y tasas en el query client', () => {
    const spy = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useInvalidateCxC(), { wrapper });

    act(() => result.current());

    expect(spy).toHaveBeenCalledWith({ queryKey: cxcKeys.carteraAll() });
    expect(spy).toHaveBeenCalledWith({ queryKey: cxcKeys.acuerdosAll() });
    expect(spy).toHaveBeenCalledWith({ queryKey: cxcKeys.tasasAll() });
  });
});
