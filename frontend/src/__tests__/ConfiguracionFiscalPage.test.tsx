import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
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

import { configuracionFiscalService, tasaIVAService } from '../services/fiscalService';
import ConfiguracionFiscalPage from '../pages/Fiscal/ConfiguracionFiscalPage';

const mockConfig = {
  id: 'cfg-001',
  id_empresa: 'emp-001',
  contribuyente_iva: true,
  aplica_igtf: true,
  tasa_igtf: '0.0300',
  fecha_creacion: '2026-05-28T10:00:00Z',
  fecha_actualizacion: '2026-05-28T10:00:00Z',
};

const mockTasas = [
  { id: 'tasa-001', id_empresa: 'emp-001', tipo: 'GENERAL' as const, nombre: 'IVA General', tasa: '0.160000', activo: true, fecha_creacion: '2026-05-28T10:00:00Z' },
  { id: 'tasa-002', id_empresa: 'emp-001', tipo: 'REDUCIDO' as const, nombre: 'IVA Reducido', tasa: '0.080000', activo: true, fecha_creacion: '2026-05-28T10:00:00Z' },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ConfiguracionFiscalPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('ConfiguracionFiscalPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('shows loading state initially', () => {
    vi.mocked(configuracionFiscalService.getByEmpresa).mockReturnValue(new Promise(() => {}));
    vi.mocked(tasaIVAService.getByEmpresa).mockReturnValue(new Promise(() => {}));
    renderPage();
    // El estado de carga ahora se representa con un spinner MUI (CircularProgress).
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('renders the page heading', async () => {
    vi.mocked(configuracionFiscalService.getByEmpresa).mockResolvedValue(mockConfig);
    vi.mocked(tasaIVAService.getByEmpresa).mockResolvedValue(mockTasas);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/configuración fiscal/i)).toBeInTheDocument();
    });
  });

  it('shows IVA section', async () => {
    vi.mocked(configuracionFiscalService.getByEmpresa).mockResolvedValue(mockConfig);
    vi.mocked(tasaIVAService.getByEmpresa).mockResolvedValue([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Impuesto al Valor Agregado/i)).toBeInTheDocument();
    });
  });

  it('shows IGTF section', async () => {
    vi.mocked(configuracionFiscalService.getByEmpresa).mockResolvedValue(mockConfig);
    vi.mocked(tasaIVAService.getByEmpresa).mockResolvedValue([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/IGTF/i)).toBeInTheDocument();
    });
  });

  it('shows IVA rate when tasas are loaded', async () => {
    vi.mocked(configuracionFiscalService.getByEmpresa).mockResolvedValue(mockConfig);
    vi.mocked(tasaIVAService.getByEmpresa).mockResolvedValue(mockTasas);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('IVA General')).toBeInTheDocument();
      expect(screen.getByText('IVA Reducido')).toBeInTheDocument();
    });
  });

  it('shows save button', async () => {
    vi.mocked(configuracionFiscalService.getByEmpresa).mockResolvedValue(mockConfig);
    vi.mocked(tasaIVAService.getByEmpresa).mockResolvedValue([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /guardar configuración/i })).toBeInTheDocument();
    });
  });

  it('calls update on save when config exists', async () => {
    vi.mocked(configuracionFiscalService.getByEmpresa).mockResolvedValue(mockConfig);
    vi.mocked(tasaIVAService.getByEmpresa).mockResolvedValue([]);
    vi.mocked(configuracionFiscalService.update).mockResolvedValue(mockConfig);
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: /guardar configuración/i }));

    fireEvent.click(screen.getByRole('button', { name: /guardar configuración/i }));
    await waitFor(() => {
      expect(configuracionFiscalService.update).toHaveBeenCalledWith('cfg-001', expect.any(Object));
    });
  });

  it('shows success message after save', async () => {
    vi.mocked(configuracionFiscalService.getByEmpresa).mockResolvedValue(mockConfig);
    vi.mocked(tasaIVAService.getByEmpresa).mockResolvedValue([]);
    vi.mocked(configuracionFiscalService.update).mockResolvedValue(mockConfig);
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: /guardar configuración/i }));
    fireEvent.click(screen.getByRole('button', { name: /guardar configuración/i }));
    await waitFor(() => {
      expect(screen.getByText(/configuración fiscal guardada/i)).toBeInTheDocument();
    });
  });
});
