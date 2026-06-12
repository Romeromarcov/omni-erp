import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/comprasService', () => ({
  comprasService: {
    getOrdenesPaginated: vi.fn(),
  },
}));

import { comprasService } from '../services/comprasService';
import OrdenesCompraListPage from '../pages/Compras/OrdenesCompraListPage';

const pagina = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id_orden_compra: 'oc-1111',
      id_empresa: 'emp-1',
      id_proveedor: 'prov-1',
      tipo_operacion: null,
      fecha_cierre_estimada: null,
      numero_orden: 'OC-0001',
      fecha_orden: '2026-06-10',
      estado: 'BORRADOR',
      observaciones: null,
      activo: true,
      fecha_creacion: '2026-06-10T12:00:00Z',
    },
    {
      id_orden_compra: 'oc-2222',
      id_empresa: 'emp-1',
      id_proveedor: 'prov-2',
      tipo_operacion: null,
      fecha_cierre_estimada: null,
      numero_orden: 'OC-0002',
      fecha_orden: '2026-06-11',
      estado: 'APROBADA',
      observaciones: null,
      activo: true,
      fecha_creacion: '2026-06-11T12:00:00Z',
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/compras/ordenes']}>
        <Routes>
          <Route path="/compras/ordenes" element={<OrdenesCompraListPage />} />
          <Route path="/compras/ordenes/nueva" element={<div>form-oc</div>} />
          <Route path="/compras/ordenes/:id" element={<div>detalle-oc</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('OrdenesCompraListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(comprasService.getOrdenesPaginated).mockResolvedValue(pagina);
  });

  afterEach(() => {
    cleanup();
  });

  it('lista las órdenes con número, fecha y estado', async () => {
    renderPage();
    expect(await screen.findByText('OC-0001')).toBeInTheDocument();
    expect(screen.getByText('OC-0002')).toBeInTheDocument();
    expect(screen.getByText('2026-06-10')).toBeInTheDocument();
    expect(screen.getByText('BORRADOR')).toBeInTheDocument();
    expect(screen.getByText('APROBADA')).toBeInTheDocument();
  });

  it('navega al detalle con "Ver detalle"', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('OC-0001');
    await user.click(screen.getAllByRole('button', { name: /ver detalle/i })[0]);
    expect(await screen.findByText('detalle-oc')).toBeInTheDocument();
  });

  it('navega al formulario con "Nueva orden"', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('OC-0001');
    await user.click(screen.getByRole('button', { name: /nueva orden/i }));
    expect(await screen.findByText('form-oc')).toBeInTheDocument();
  });

  it('muestra el mensaje vacío si no hay órdenes', async () => {
    vi.mocked(comprasService.getOrdenesPaginated).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    renderPage();
    expect(await screen.findByText(/no hay órdenes de compra/i)).toBeInTheDocument();
  });
});
