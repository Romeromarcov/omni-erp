import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/fiscalService', () => ({
  configuracionFiscalService: {
    getByEmpresa: vi.fn(),
    update: vi.fn(),
    create: vi.fn(),
  },
  tasaIVAService: {
    getByEmpresa: vi.fn(),
    update: vi.fn(),
    create: vi.fn(),
  },
  libroService: {
    fetchLibroVentasTxt: vi.fn(),
    fetchLibroComprasTxt: vi.fn(),
    downloadLibroVentasTxt: vi.fn(),
    downloadLibroComprasTxt: vi.fn(),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { empresas: [{ id_empresa: 'emp-001' }] },
    token: 'test-token',
  }),
}));

import { libroService } from '../services/fiscalService';
import LibroVentasPage from '../pages/Fiscal/LibroVentasPage';
import LibroComprasPage from '../pages/Fiscal/LibroComprasPage';

const mockEntries = [
  {
    rif_emisor: 'J-12345678-9',
    rif_receptor: 'V-98765432-1',
    fecha: '2026-05-10',
    nro_ctrl: '00000001',
    nro_fac: 'FAC-0001',
    base_imponible: '1000.00',
    iva: '160.00',
    total: '1160.00',
  },
  {
    rif_emisor: 'J-12345678-9',
    rif_receptor: 'V-11223344-5',
    fecha: '2026-05-15',
    nro_ctrl: '00000002',
    nro_fac: 'FAC-0002',
    base_imponible: '2000.00',
    iva: '320.00',
    total: '2320.00',
  },
];

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderVentas() {
  return render(
    <QueryClientProvider client={makeQC()}>
      <MemoryRouter>
        <LibroVentasPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderCompras() {
  return render(
    <QueryClientProvider client={makeQC()}>
      <MemoryRouter>
        <LibroComprasPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('LibroVentasPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the page heading', () => {
    renderVentas();
    expect(screen.getByRole('heading', { name: /libro de ventas/i })).toBeInTheDocument();
  });

  it('shows a period input and Consultar button', () => {
    renderVentas();
    expect(screen.getByRole('button', { name: /consultar/i })).toBeInTheDocument();
  });

  it('fetches and shows entries after Consultar click', async () => {
    vi.mocked(libroService.fetchLibroVentasTxt).mockResolvedValue(mockEntries);
    renderVentas();

    fireEvent.click(screen.getByRole('button', { name: /consultar/i }));

    await waitFor(() => {
      expect(screen.getByText('FAC-0001')).toBeInTheDocument();
      expect(screen.getByText('FAC-0002')).toBeInTheDocument();
    });
  });

  it('shows summary cards with correct totals', async () => {
    vi.mocked(libroService.fetchLibroVentasTxt).mockResolvedValue(mockEntries);
    renderVentas();
    fireEvent.click(screen.getByRole('button', { name: /consultar/i }));

    await waitFor(() => {
      // Total count: 2
      expect(screen.getByText('2')).toBeInTheDocument();
    });
  });

  it('shows empty message when no entries', async () => {
    vi.mocked(libroService.fetchLibroVentasTxt).mockResolvedValue([]);
    renderVentas();
    fireEvent.click(screen.getByRole('button', { name: /consultar/i }));

    await waitFor(() => {
      expect(screen.getByText(/no hay facturas en el período/i)).toBeInTheDocument();
    });
  });

  it('shows Exportar TXT button when entries exist', async () => {
    vi.mocked(libroService.fetchLibroVentasTxt).mockResolvedValue(mockEntries);
    renderVentas();
    fireEvent.click(screen.getByRole('button', { name: /consultar/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /exportar txt/i })).toBeInTheDocument();
    });
  });
});

describe('LibroComprasPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the page heading', () => {
    renderCompras();
    expect(screen.getByRole('heading', { name: /libro de compras/i })).toBeInTheDocument();
  });

  it('shows Consultar button', () => {
    renderCompras();
    expect(screen.getByRole('button', { name: /consultar/i })).toBeInTheDocument();
  });

  it('fetches and shows entries after Consultar click', async () => {
    vi.mocked(libroService.fetchLibroComprasTxt).mockResolvedValue(mockEntries);
    renderCompras();

    fireEvent.click(screen.getByRole('button', { name: /consultar/i }));

    await waitFor(() => {
      expect(screen.getByText('FAC-0001')).toBeInTheDocument();
    });
  });

  it('shows empty message when no entries', async () => {
    vi.mocked(libroService.fetchLibroComprasTxt).mockResolvedValue([]);
    renderCompras();
    fireEvent.click(screen.getByRole('button', { name: /consultar/i }));

    await waitFor(() => {
      expect(screen.getByText(/no hay facturas de compra en el período/i)).toBeInTheDocument();
    });
  });
});
