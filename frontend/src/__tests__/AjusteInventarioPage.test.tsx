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

import {
  stockActualService,
  productoInventarioService,
  movimientoService,
} from '../services/inventarioService';
import AjusteInventarioPage from '../pages/Inventario/AjusteInventarioPage';

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
    cantidad_disponible: '5.0000',
    cantidad_comprometida: '0.0000',
    cantidad_en_transito: '0.0000',
    cantidad_minima: '20.0000',
    cantidad_maxima: '200.0000',
    fecha_ultima_actualizacion: '2026-05-28T10:00:00Z',
    producto_nombre: 'Producto B',
    almacen_nombre: 'Almacén Principal',
  },
];

const mockProductos = [
  { id_producto: 'prod-001', nombre_producto: 'Producto A', sku: 'SKU-A' },
  { id_producto: 'prod-002', nombre_producto: 'Producto B', sku: 'SKU-B' },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AjusteInventarioPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AjusteInventarioPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the page heading', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/ajuste manual de inventario/i)).toBeInTheDocument();
    });
  });

  it('renders Producto and Almacén dropdowns', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/seleccionar producto/i)).toBeInTheDocument();
      expect(screen.getByText(/seleccionar almacén/i)).toBeInTheDocument();
    });
  });

  it('lists products in the dropdown', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Producto A \(SKU-A\)/)).toBeInTheDocument();
      expect(screen.getByText(/Producto B \(SKU-B\)/)).toBeInTheDocument();
    });
  });

  it('shows ENTRADA and SALIDA radio options', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/entrada de inventario/i)).toBeInTheDocument();
      expect(screen.getByText(/salida de inventario/i)).toBeInTheDocument();
    });
  });

  it('shows Registrar ajuste submit button', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /registrar ajuste/i })).toBeInTheDocument();
    });
  });

  it('shows Cancelar button', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancelar/i })).toBeInTheDocument();
    });
  });

  it('shows stock info panel when product and warehouse are selected', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    renderPage();

    await waitFor(() => screen.getByText(/Producto A \(SKU-A\)/));

    // Select product
    const productoSelect = screen.getByDisplayValue('— Seleccionar producto —');
    fireEvent.change(productoSelect, { target: { value: 'prod-001' } });

    // Select warehouse
    const almacenSelect = screen.getByDisplayValue('— Seleccionar almacén —');
    fireEvent.change(almacenSelect, { target: { value: 'alm-001' } });

    await waitFor(() => {
      expect(screen.getByText(/stock actual:/i)).toBeInTheDocument();
    });
  });

  it('shows success message after successful submission', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    vi.mocked(movimientoService.registrarAjuste).mockResolvedValue({ id_movimiento_inventario: 'new-001' } as never);

    renderPage();
    await waitFor(() => screen.getByText(/Producto A \(SKU-A\)/));

    // Fill product
    fireEvent.change(screen.getByDisplayValue('— Seleccionar producto —'), {
      target: { value: 'prod-001' },
    });
    // Fill warehouse
    fireEvent.change(screen.getByDisplayValue('— Seleccionar almacén —'), {
      target: { value: 'alm-001' },
    });
    // Fill cantidad
    const cantidadInput = screen.getByPlaceholderText(/ej: 50/i);
    fireEvent.change(cantidadInput, { target: { value: '10' } });

    // Submit
    fireEvent.click(screen.getByRole('button', { name: /registrar ajuste/i }));

    await waitFor(() => {
      expect(screen.getByText(/ajuste registrado correctamente/i)).toBeInTheDocument();
    });
  });

  it('shows error message when submission fails', async () => {
    vi.mocked(stockActualService.getAll).mockResolvedValue(mockStock);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue(mockProductos as never[]);
    vi.mocked(movimientoService.registrarAjuste).mockRejectedValue(new Error('Error de servidor'));

    renderPage();
    await waitFor(() => screen.getByText(/Producto A \(SKU-A\)/));

    fireEvent.change(screen.getByDisplayValue('— Seleccionar producto —'), {
      target: { value: 'prod-001' },
    });
    fireEvent.change(screen.getByDisplayValue('— Seleccionar almacén —'), {
      target: { value: 'alm-001' },
    });
    const cantidadInput = screen.getByPlaceholderText(/ej: 50/i);
    fireEvent.change(cantidadInput, { target: { value: '5' } });

    fireEvent.click(screen.getByRole('button', { name: /registrar ajuste/i }));

    await waitFor(() => {
      expect(screen.getByText(/error de servidor/i)).toBeInTheDocument();
    });
  });
});
