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
import FacturasFiscalesListPage from '../pages/Ventas/FacturasFiscales/FacturasFiscalesListPage';

const mockFacturas = [
  {
    id_factura: 'fac-001',
    numero_factura: 'F-0001',
    numero_control: '00-0001',
    fecha_emision: '2024-02-10',
    estado: 'EMITIDA',
    id_nota_venta_origen: null,
    id_cliente: {
      id_cliente: 'cli-001',
      nombre: 'Juan Pérez',
      razon_social: 'Empresa A',
      rif: 'V-12345678-9',
    },
    detalles: [
      { id_detalle: 'd1', total_linea: 100.0 },
      { id_detalle: 'd2', total_linea: 200.0 },
    ],
  },
  {
    id_factura: 'fac-002',
    numero_factura: 'F-0002',
    numero_control: '00-0002',
    fecha_emision: '2024-02-15',
    estado: 'PAGADA',
    id_nota_venta_origen: 'nv-001',
    id_cliente: {
      id_cliente: 'cli-002',
      nombre: 'María García',
      razon_social: 'Empresa B',
      rif: 'J-98765432-1',
    },
    detalles: [],
  },
];

function renderFacturasFiscalesListPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FacturasFiscalesListPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('FacturasFiscalesListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    vi.mocked(get).mockReturnValue(new Promise(() => {}));
    renderFacturasFiscalesListPage();
    expect(screen.getByText(/cargando facturas fiscales/i)).toBeInTheDocument();
  });

  it('renders facturas list after data loads', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockFacturas, count: 2, next: null, previous: null });
    renderFacturasFiscalesListPage();

    await waitFor(() => {
      expect(screen.getByText('F-0001')).toBeInTheDocument();
      expect(screen.getByText('F-0002')).toBeInTheDocument();
    });
  });

  it('shows title and new factura button', async () => {
    vi.mocked(get).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    renderFacturasFiscalesListPage();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /^facturas fiscales$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /nueva factura fiscal/i })).toBeInTheDocument();
    });
  });

  it('shows empty state when no facturas', async () => {
    vi.mocked(get).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    renderFacturasFiscalesListPage();

    await waitFor(() => {
      expect(screen.getByText(/no hay facturas fiscales registradas/i)).toBeInTheDocument();
    });
  });

  it('renders table headers when data is present', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockFacturas, count: 2, next: null, previous: null });
    renderFacturasFiscalesListPage();

    await waitFor(() => {
      expect(screen.getByText(/número/i)).toBeInTheDocument();
      expect(screen.getByText(/cliente/i)).toBeInTheDocument();
      expect(screen.getByText(/estado/i)).toBeInTheDocument();
    });
  });

  it('shows origin column with nota venta label', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockFacturas, count: 2, next: null, previous: null });
    renderFacturasFiscalesListPage();

    await waitFor(() => {
      // fac-002 has id_nota_venta_origen set
      expect(screen.getByText('Nota Venta')).toBeInTheDocument();
      // fac-001 has no origin (direct)
      expect(screen.getByText('Directa')).toBeInTheDocument();
    });
  });
});
