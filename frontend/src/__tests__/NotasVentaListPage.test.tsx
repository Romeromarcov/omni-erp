import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock services/api
vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  fetcher: vi.fn(),
}));

import { get } from '../services/api';
import NotasVentaListPage from '../pages/Ventas/NotasVenta/NotasVentaListPage';

const mockNotasVenta = [
  {
    id_nota_venta: 'nv-001',
    numero_nota: 'NV-0001',
    fecha_nota: '2024-03-05',
    estado: 'BORRADOR',
    convertido_a_factura: false,
    id_pedido_origen: null,
    id_cliente: {
      id_cliente: 'cli-001',
      nombre: 'Juan Pérez',
      razon_social: 'Empresa A',
      rif: 'V-12345678-9',
    },
  },
  {
    id_nota_venta: 'nv-002',
    numero_nota: 'NV-0002',
    fecha_nota: '2024-03-10',
    estado: 'FACTURADA',
    convertido_a_factura: true,
    id_pedido_origen: 'ped-001',
    id_cliente: {
      id_cliente: 'cli-002',
      nombre: 'María García',
      razon_social: 'Empresa B',
      rif: 'J-98765432-1',
    },
  },
];

function renderNotasVentaListPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NotasVentaListPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('NotasVentaListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    vi.mocked(get).mockReturnValue(new Promise(() => {}));
    renderNotasVentaListPage();
    expect(screen.getByText(/cargando notas de venta/i)).toBeInTheDocument();
  });

  it('renders notas venta list after data loads', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockNotasVenta, count: 2, next: null, previous: null });
    renderNotasVentaListPage();

    await waitFor(() => {
      expect(screen.getByText('NV-0001')).toBeInTheDocument();
      expect(screen.getByText('NV-0002')).toBeInTheDocument();
    });
  });

  it('shows title and new nota venta button', async () => {
    vi.mocked(get).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    renderNotasVentaListPage();

    expect(screen.getByText(/gestión de notas de venta/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /nueva nota de venta/i })).toBeInTheDocument();
  });

  it('shows empty state when no notas venta', async () => {
    vi.mocked(get).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    renderNotasVentaListPage();

    await waitFor(() => {
      expect(screen.getByText(/no hay notas de venta registradas/i)).toBeInTheDocument();
    });
  });

  it('shows converted badge for facturada nota', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockNotasVenta, count: 2, next: null, previous: null });
    renderNotasVentaListPage();

    await waitFor(() => {
      expect(screen.getByText(/✓ convertido/i)).toBeInTheDocument();
    });
  });

  it('shows "De Pedido" origin for nota with pedido origen', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockNotasVenta, count: 2, next: null, previous: null });
    renderNotasVentaListPage();

    await waitFor(() => {
      expect(screen.getByText(/✓ de pedido/i)).toBeInTheDocument();
      expect(screen.getByText(/^manual$/i)).toBeInTheDocument();
    });
  });
});
