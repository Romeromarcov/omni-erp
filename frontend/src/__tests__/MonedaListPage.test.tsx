import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock services/api
vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

import { get } from '../services/api';
import MonedaListPage from '../pages/Finanzas/Monedas/MonedaListPage';

const mockMonedas = [
  {
    id_moneda: '1',
    tipo_moneda: 'fiat' as const,
    codigo_iso: 'USD',
    nombre: 'Dólar Americano',
    simbolo: '$',
    decimales: 2,
    activo: true,
  },
  {
    id_moneda: '2',
    tipo_moneda: 'fiat' as const,
    codigo_iso: 'VES',
    nombre: 'Bolívar Soberano',
    simbolo: 'Bs',
    decimales: 2,
    activo: true,
  },
];

function renderMonedaListPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <MonedaListPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('MonedaListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', async () => {
    // Never resolve so loading stays visible
    vi.mocked(get).mockReturnValue(new Promise(() => {}));
    renderMonedaListPage();
    expect(screen.getByText(/cargando/i)).toBeInTheDocument();
  });

  it('renders moneda list after data loads', async () => {
    vi.mocked(get).mockImplementation((endpoint: string) => {
      if (endpoint.includes('monedas-empresa-activas')) {
        return Promise.resolve([]);
      }
      return Promise.resolve(mockMonedas);
    });

    renderMonedaListPage();

    await waitFor(() => {
      expect(screen.getByText('USD')).toBeInTheDocument();
      expect(screen.getByText('VES')).toBeInTheDocument();
    });
  });

  it('renders search input and nueva moneda link', async () => {
    vi.mocked(get).mockResolvedValue([]);
    renderMonedaListPage();

    expect(screen.getByPlaceholderText(/buscar/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /nueva moneda/i })).toBeInTheDocument();
  });
});
