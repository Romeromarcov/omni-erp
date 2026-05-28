import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock services
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
import InventarioDashboardPage from '../pages/Inventario/InventarioDashboardPage';

const mockStock = [
  {
    id_stock_actual: 'sa-001',
    id_empresa: 'emp-001',
    id_producto: 'prod-001',
    id_almacen: 'alm-001',
    cantidad_disponible: '100.0000',
    cantidad_comprometida: '10.0000',
    cantidad_en_transito: '0.0000',
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
    cantidad_disponible: '5.0000',   // below minimum of 20
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
    id_almacen: 'alm-001',
    cantidad_disponible: '0.0000',   // critical - zero stock
    cantidad_comprometida: '0.0000',
    cantidad_en_transito: '0.0000',
    cantidad_minima: '10.0000',
    cantidad_maxima: '100.0000',
    fecha_ultima_actualizacion: '2026-05-28T10:00:00Z',
    producto_nombre: 'Producto C',
    almacen_nombre: 'Almacén Norte',
  },
];

const mockProductos = [
  { id_producto: 'prod-001', nombre_producto: 'Producto A', sku: 'SKU-A' },
  { id_producto: 'prod-002', nombre_producto: 'Producto B', sku: 'SKU-B' },
  { id_producto: 'prod-003', nombre_producto: 'Producto C', sku: 'SKU-C' },
];

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <InventarioDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('InventarioDashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    vi.mocked(stockActualService.getAll).mockReturnValue(new Promise(() => {}));
    vi.mocked(productoInventarioService.getAll).mockReturnValue(new Promise(() => {}));
    renderDashboard();
    expect(screen.getByText(/cargando inventario/i)).toBeInTheDocument();
  });

  it('renders dashboard title', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/dashboard de inventario/i)).toBeInTheDocument();
    });
  });

  it('shows correct KPI for total productos', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('3')).toBeInTheDocument(); // 3 productos
    });
  });

  it('shows alert table with low-stock products', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderDashboard();

    await waitFor(() => {
      // Both "Producto B" (bajo) and "Producto C" (critico) should appear
      expect(screen.getByText('Producto B')).toBeInTheDocument();
      expect(screen.getByText('Producto C')).toBeInTheDocument();
    });
  });

  it('shows SIN STOCK badge for zero-stock products', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('SIN STOCK')).toBeInTheDocument();
    });
  });

  it('shows BAJO badge for below-minimum products', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('BAJO')).toBeInTheDocument();
    });
  });

  it('shows all-ok message when no stock alerts', async () => {
    const normalStock = mockStock.map((s) => ({ ...s, cantidad_disponible: '100.0000' }));
    vi.mocked(stockActualService.getAll).mockResolvedValue(normalStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/todos los productos están sobre el stock mínimo/i)).toBeInTheDocument();
    });
  });

  it('shows action buttons (ver stock + registrar ajuste)', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue([]);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue([]);
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /ver stock completo/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /registrar ajuste/i })).toBeInTheDocument();
    });
  });
});
