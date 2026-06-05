/**
 * TEST-6 — Test de hook con MSW (red real, sin mockear services/api).
 *
 * `useEmpresas` → `fetchEmpresas` (services/empresas.ts) → `get` (services/api.ts)
 * → `fetch` interceptado por MSW. Verifica el camino completo de datos: el hook
 * no se mockea; la única frontera falsa es la respuesta HTTP.
 */
import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import { http, HttpResponse } from 'msw';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEmpresas } from '../hooks/useEmpresas';
import { server } from '../test/server';
import { apiUrl } from '../test/handlers';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('useEmpresas (MSW)', () => {
  it('carga las empresas desde el endpoint real /core/empresas/', async () => {
    const { result } = renderHook(() => useEmpresas(), { wrapper });

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].nombre_comercial).toBe('Demo');
    expect(result.current.data?.[0].id_empresa).toBe('emp-1');
  });

  it('propaga el error cuando el backend responde 500', async () => {
    server.use(
      http.get(apiUrl('/core/empresas/'), () =>
        HttpResponse.json({ error: 'boom' }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useEmpresas(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });
});
