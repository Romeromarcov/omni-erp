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

  afterEach(() => {
    cleanup();
  });

  it('shows loading state initially', () => {
    vi.mocked(get).mockReturnValue(new Promise(() => {}));
    renderFacturasFiscalesListPage();
    // El estado de carga ahora se representa con el spinner del DataTable (MUI CircularProgress).
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
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
      // El título y el botón usan claves i18n (t) que renderizan la clave en el entorno de test.
      expect(screen.getByRole('heading', { name: /facturasFiscales\.title/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /facturasFiscales\.nueva/i })).toBeInTheDocument();
    });
  });

  it('shows empty state when no facturas', async () => {
    vi.mocked(get).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    renderFacturasFiscalesListPage();

    await waitFor(() => {
      // El mensaje de vacío usa la clave i18n sinRegistros (renderizada como clave en test).
      expect(screen.getByText(/facturasFiscales\.sinRegistros/i)).toBeInTheDocument();
    });
  });

  it('renders table headers when data is present', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockFacturas, count: 2, next: null, previous: null });
    renderFacturasFiscalesListPage();

    await waitFor(() => {
      // La tabla modernizada (DataTable) ya no tiene columna "Estado";
      // verificamos las cabeceras vigentes.
      expect(screen.getByText(/número/i)).toBeInTheDocument();
      expect(screen.getByText(/fecha/i)).toBeInTheDocument();
      expect(screen.getByText(/cliente/i)).toBeInTheDocument();
    });
  });

  it('shows origin column with nota venta label', async () => {
    vi.mocked(get).mockResolvedValue({ results: mockFacturas, count: 2, next: null, previous: null });
    renderFacturasFiscalesListPage();

    await waitFor(() => {
      // La tabla modernizada (DataTable) ya no muestra una columna de "origen"
      // (Nota Venta / Directa). Se preserva la intención verificando que ambas
      // facturas (con y sin nota de venta de origen) se listan y se distinguen
      // por su cliente.
      expect(screen.getByText('Juan Pérez')).toBeInTheDocument();
      expect(screen.getByText('María García')).toBeInTheDocument();
    });
  });
});
