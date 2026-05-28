import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/inventarioService', () => ({
  stockActualService: {
    getAll: vi.fn(),
    getBajoMinimo: vi.fn(),
  },
  productoInventarioService: {
    getAll: vi.fn(),
    getById: vi.fn(),
    getKardex: vi.fn(),
  },
  movimientoService: {
    registrarAjuste: vi.fn(),
  },
}));

import { stockActualService, productoInventarioService } from '../services/inventarioService';
import StockActualPage from '../pages/Inventario/StockActualPage';

const mockStock = [
  {
    id_stock_actual: 'sa-001',
    id_empresa: 'emp-001',
    id_producto: 'prod-001',
    id_almacen: 'alm-001',
    cantidad_disponible: '100.0000',
    cantidad_comprometida: '10.0000',
    cantidad_en_transito: '5.0000',
    cantidad_minima: '20.0000',
    cantidad_maxima: '500.0000',
    fecha_ultima_actualizacion: '2026-05-28T10:00:00Z',
    producto_nombre: 'Producto A',
    almacen_nombre: 'Almacén Principal',
  },
  {
    id_stock_actual: 'sa-002',
    id_empresa: 'emp-001',
    id_producto: 'prod-002',
    id_almacen: 'alm-001',
    cantidad_disponible: '5.0000',
    cantidad_comprometida: '0.0000',
    cantidad_en_transito: '0.0000',
    cantidad_minima: '20.0000',
    cantidad_maxima: '200.0000',
    fecha_ultima_actualizacion: '2026-05-28T10:00:00Z',
    producto_nombre: 'Producto B',
    almacen_nombre: 'Almacén Principal',
  },
  {
    id_stock_actual: 'sa-003',
    id_empresa: 'emp-001',
    id_producto: 'prod-003',
    id_almacen: 'alm-002',
    cantidad_disponible: '0.0000',
    cantidad_comprometida: '0.0000',
    cantidad_en_transito: '0.0000',
    cantidad_minima: '10.0000',
    cantidad_maxima: '100.0000',
    fecha_ultima_actualizacion: '2026-05-28T09:00:00Z',
    producto_nombre: 'Producto C',
    almacen_nombre: 'Almacén Norte',
  },
];

const mockProductos = [
  { id_producto: 'prod-001', nombre_producto: 'Producto A', sku: 'SKU-A' },
  { id_producto: 'prod-002', nombre_producto: 'Producto B', sku: 'SKU-B' },
  { id_producto: 'prod-003', nombre_producto: 'Producto C', sku: 'SKU-C' },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <StockActualPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('StockActualPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    vi.mocked(stockActualService.getAll).mockReturnValue(new Promise(() => {}));
    vi.mocked(productoInventarioService.getAll).mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText(/cargando stock/i)).toBeInTheDocument();
  });

  it('renders the page heading', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Stock Actual')).toBeInTheDocument();
    });
  });

  it('renders all stock rows after loading', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Producto A')).toBeInTheDocument();
      expect(screen.getByText('Producto B')).toBeInTheDocument();
      expect(screen.getByText('Producto C')).toBeInTheDocument();
    });
  });

  it('shows NORMAL badge for adequate stock', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('NORMAL')).toBeInTheDocument();
    });
  });

  it('shows BAJO badge for below-minimum stock', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('BAJO')).toBeInTheDocument();
    });
  });

  it('shows SIN STOCK badge for zero stock', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('SIN STOCK')).toBeInTheDocument();
    });
  });

  it('filters rows by product name', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => screen.getByText('Producto A'));

    const searchInput = screen.getByPlaceholderText(/buscar producto/i);
    fireEvent.change(searchInput, { target: { value: 'Producto A' } });

    expect(screen.getByText('Producto A')).toBeInTheDocument();
    expect(screen.queryByText('Producto B')).not.toBeInTheDocument();
    expect(screen.queryByText('Producto C')).not.toBeInTheDocument();
  });

  it('shows empty message when no rows match filters', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => screen.getByText('Producto A'));

    const searchInput = screen.getByPlaceholderText(/buscar producto/i);
    fireEvent.change(searchInput, { target: { value: 'xyzxyzxyz' } });

    expect(screen.getByText(/no hay registros con los filtros seleccionados/i)).toBeInTheDocument();
  });

  it('shows "Ajuste manual" action button in header', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /ajuste manual/i })).toBeInTheDocument();
    });
  });

  it('shows Kardex and Ajuste buttons per row', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      const kardexBtns = screen.getAllByRole('button', { name: /kardex/i });
      const ajusteBtns = screen.getAllByRole('button', { name: /ajuste/i });
      expect(kardexBtns.length).toBe(3);
      // 3 row-level Ajuste buttons + 1 header "+ Ajuste manual"
      expect(ajusteBtns.length).toBeGreaterThanOrEqual(3);
    });
  });
});
