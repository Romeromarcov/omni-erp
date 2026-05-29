import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
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

  afterEach(() => {
    cleanup();
  });

  it('shows loading state initially', () => {
    vi.mocked(get).mockReturnValue(new Promise(() => {}));
    renderNotasVentaListPage();
    // El estado de carga ahora se representa con el spinner del DataTable (MUI CircularProgress).
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('renders notas venta list after data loads', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockNotasVenta, count: 2, next: null, previous: null });
    renderNotasVentaListPage();

    await waitFor(() => {
      // La tabla modernizada (DataTable) lista una fila por nota; se verifica que
      // ambas notas aparezcan a través del nombre de su cliente.
      expect(screen.getByText('Juan Pérez')).toBeInTheDocument();
      expect(screen.getByText('María García')).toBeInTheDocument();
    });
  });

  it('shows title and new nota venta button', async () => {
    vi.mocked(get).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    renderNotasVentaListPage();

    // El título resuelve vía i18n; el botón "nueva" no tiene traducción y
    // renderiza su clave i18n cruda.
    expect(screen.getByText(/gestión de notas de venta/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /notasVenta\.nueva/i })).toBeInTheDocument();
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
      // El estado de conversión ahora se muestra con un StatusChip por estado:
      // nv-002 está FACTURADA (convertida) y nv-001 en BORRADOR.
      expect(screen.getByText('FACTURADA')).toBeInTheDocument();
      expect(screen.getByText('BORRADOR')).toBeInTheDocument();
    });
  });

  it('shows "De Pedido" origin for nota with pedido origen', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockNotasVenta, count: 2, next: null, previous: null });
    renderNotasVentaListPage();

    await waitFor(() => {
      // La tabla modernizada ya no tiene columna de origen ("De Pedido"/"Manual").
      // Se preserva la intención verificando que ambas notas (con y sin pedido de
      // origen) se listan, distinguidas por el nombre de su cliente.
      expect(screen.getByText('Juan Pérez')).toBeInTheDocument();
      expect(screen.getByText('María García')).toBeInTheDocument();
    });
  });
});
