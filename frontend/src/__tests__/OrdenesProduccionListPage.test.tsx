import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/manufacturaService', () => ({
  manufacturaService: {
    getOrdenesPaginated: vi.fn(),
  },
}));

import { manufacturaService } from '../services/manufacturaService';
import OrdenesProduccionListPage from '../pages/Manufactura/OrdenesProduccionListPage';

const pagina = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 'of-aaaa1111-0000-0000-0000-000000000000',
      producto: 'prod-1',
      cantidad: '10.00',
      fecha_inicio: '2026-06-01',
      fecha_fin: null,
      estado: 'en_proceso',
      lista_materiales: 'bom-1',
      ruta_produccion: null,
      referencia_externa: 'OF-0001',
      observaciones: '',
    },
    {
      id: 'of-bbbb2222-0000-0000-0000-000000000000',
      producto: 'prod-2',
      cantidad: '5.00',
      fecha_inicio: '2026-06-05',
      fecha_fin: null,
      estado: 'pendiente',
      lista_materiales: null,
      ruta_produccion: null,
      referencia_externa: '',
      observaciones: '',
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/manufactura/ordenes']}>
        <Routes>
          <Route path="/manufactura/ordenes" element={<OrdenesProduccionListPage />} />
          <Route path="/manufactura/ordenes/:id" element={<div>detalle-of</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('OrdenesProduccionListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(manufacturaService.getOrdenesPaginated).mockResolvedValue(pagina);
  });

  afterEach(() => {
    cleanup();
  });

  it('lista las órdenes con referencia, cantidad y estado', async () => {
    renderPage();
    expect(await screen.findByText('OF-0001')).toBeInTheDocument();
    // Sin referencia externa cae al id corto.
    expect(screen.getByText('OF-of-bbbb2')).toBeInTheDocument();
    expect(screen.getByText('10.00')).toBeInTheDocument();
    expect(screen.getByText('en_proceso')).toBeInTheDocument();
  });

  it('navega al detalle con "Ver detalle"', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('OF-0001');
    await user.click(screen.getAllByRole('button', { name: /ver detalle/i })[0]);
    expect(await screen.findByText('detalle-of')).toBeInTheDocument();
  });

  it('muestra el mensaje vacío si no hay órdenes', async () => {
    vi.mocked(manufacturaService.getOrdenesPaginated).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    renderPage();
    expect(await screen.findByText(/no hay órdenes de producción/i)).toBeInTheDocument();
  });
});
