import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

// Mock services/api
vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  fetcher: vi.fn(),
}));

import { get } from '../services/api';
import PedidosListPage from '../pages/Ventas/Pedidos/PedidosListPage';

const mockPedidos = [
  {
    id_pedido: 'ped-001',
    numero_pedido: 'P-0001',
    fecha_pedido: '2024-01-15',
    estado: 'PENDIENTE',
    convertido_a_nota_venta: false,
    id_cotizacion_origen: null,
    id_cliente: {
      id_cliente: 'cli-001',
      nombre: 'Juan Pérez',
      razon_social: 'Empresa A',
      rif: 'V-12345678-9',
    },
  },
  {
    id_pedido: 'ped-002',
    numero_pedido: 'P-0002',
    fecha_pedido: '2024-01-20',
    estado: 'APROBADO',
    convertido_a_nota_venta: true,
    id_cotizacion_origen: 'cot-001',
    id_cliente: {
      id_cliente: 'cli-002',
      nombre: 'María García',
      razon_social: 'Empresa B',
      rif: 'J-98765432-1',
    },
  },
];

function renderPedidosListPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FeedbackProvider>
          <PedidosListPage />
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('PedidosListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('shows loading state initially', () => {
    vi.mocked(get).mockReturnValue(new Promise(() => {}));
    renderPedidosListPage();
    // El estado de carga ahora se representa con el spinner del DataTable (MUI CircularProgress).
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('renders pedidos list after data loads', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockPedidos, count: 2, next: null, previous: null });
    renderPedidosListPage();

    await waitFor(() => {
      expect(screen.getByText('P-0001')).toBeInTheDocument();
      expect(screen.getByText('P-0002')).toBeInTheDocument();
    });
  });

  it('shows title and new pedido button', async () => {
    vi.mocked(get).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    renderPedidosListPage();

    expect(screen.getByText(/gestión de pedidos/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /nuevo pedido/i })).toBeInTheDocument();
  });

  it('shows empty state when no pedidos', async () => {
    vi.mocked(get).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    renderPedidosListPage();

    await waitFor(() => {
      expect(screen.getByText(/no hay pedidos registrados/i)).toBeInTheDocument();
    });
  });

  it('renders table headers', async () => {
    vi.mocked(get).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    renderPedidosListPage();

    await waitFor(() => {
      expect(screen.getByText(/número/i)).toBeInTheDocument();
      expect(screen.getByText(/fecha/i)).toBeInTheDocument();
      expect(screen.getByText(/estado/i)).toBeInTheDocument();
      expect(screen.getByText(/cliente/i)).toBeInTheDocument();
    });
  });

  it('shows converted badge for already-converted pedido', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockPedidos, count: 2, next: null, previous: null });
    renderPedidosListPage();

    await waitFor(() => {
      expect(screen.getByText(/✓ convertido/i)).toBeInTheDocument();
    });
  });
});
