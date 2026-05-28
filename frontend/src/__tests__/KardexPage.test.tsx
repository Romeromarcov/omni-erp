import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
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

import { productoInventarioService } from '../services/inventarioService';
import KardexPage from '../pages/Inventario/KardexPage';

const mockProducto = {
  id_producto: 'prod-001',
  nombre_producto: 'Producto A',
  sku: 'SKU-A',
  nombre_categoria: 'Electrónica',
  nombre_unidad_medida: 'Unidad',
};

const mockMovimientos = [
  {
    id_movimiento_inventario: 'mov-001',
    id_empresa: 'emp-001',
    id_producto: 'prod-001',
    tipo_movimiento: 'ENTRADA',
    cantidad: '50.0000',
    fecha_hora_movimiento: '2026-05-01T08:00:00Z',
    almacen_origen_nombre: null,
    almacen_destino_nombre: 'Almacén Principal',
    costo_unitario_movimiento: '10.00',
    observaciones: 'Compra inicial',
  },
  {
    id_movimiento_inventario: 'mov-002',
    id_empresa: 'emp-001',
    id_producto: 'prod-001',
    tipo_movimiento: 'SALIDA',
    cantidad: '20.0000',
    fecha_hora_movimiento: '2026-05-10T14:00:00Z',
    almacen_origen_nombre: 'Almacén Principal',
    almacen_destino_nombre: null,
    costo_unitario_movimiento: null,
    observaciones: 'Despacho cliente X',
  },
  {
    id_movimiento_inventario: 'mov-003',
    id_empresa: 'emp-001',
    id_producto: 'prod-001',
    tipo_movimiento: 'AJUSTE',
    cantidad: '5.0000',
    fecha_hora_movimiento: '2026-05-20T10:00:00Z',
    almacen_origen_nombre: null,
    almacen_destino_nombre: 'Almacén Principal',
    costo_unitario_movimiento: null,
    observaciones: 'Conteo físico',
  },
];

function renderKardex(productoId = 'prod-001') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/inventario/kardex/${productoId}`]}>
        <Routes>
          <Route path="/inventario/kardex/:productoId" element={<KardexPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('KardexPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state while fetching movements', () => {
    vi.mocked(productoInventarioService.getById).mockReturnValue(new Promise(() => {}));
    vi.mocked(productoInventarioService.getKardex).mockReturnValue(new Promise(() => {}));
    renderKardex();
    expect(screen.getByText(/cargando movimientos/i)).toBeInTheDocument();
  });

  it('renders the Kardex heading with product name', async () => {
    vi.mocked(productoInventarioService.getById).mockResolvedValue(mockProducto as never);
    vi.mocked(productoInventarioService.getKardex).mockResolvedValue(mockMovimientos as never[]);
    renderKardex();
    await waitFor(() => {
      expect(screen.getByText(/kardex/i)).toBeInTheDocument();
      expect(screen.getByText(/producto a/i)).toBeInTheDocument();
    });
  });

  it('shows product SKU and category metadata', async () => {
    vi.mocked(productoInventarioService.getById).mockResolvedValue(mockProducto as never);
    vi.mocked(productoInventarioService.getKardex).mockResolvedValue(mockMovimientos as never[]);
    renderKardex();
    await waitFor(() => {
      expect(screen.getByText(/SKU-A/)).toBeInTheDocument();
      expect(screen.getByText(/Electrónica/)).toBeInTheDocument();
    });
  });

  it('renders all movement rows', async () => {
    vi.mocked(productoInventarioService.getById).mockResolvedValue(mockProducto as never);
    vi.mocked(productoInventarioService.getKardex).mockResolvedValue(mockMovimientos as never[]);
    renderKardex();
    await waitFor(() => {
      // Movement type badges (underscore replaced with space for AJUSTE → "AJUSTE", ENTRADA → "ENTRADA", SALIDA → "SALIDA")
      expect(screen.getByText('ENTRADA')).toBeInTheDocument();
      expect(screen.getByText('SALIDA')).toBeInTheDocument();
      expect(screen.getByText('AJUSTE')).toBeInTheDocument();
    });
  });

  it('calculates Total entradas summary card correctly', async () => {
    vi.mocked(productoInventarioService.getById).mockResolvedValue(mockProducto as never);
    vi.mocked(productoInventarioService.getKardex).mockResolvedValue(mockMovimientos as never[]);
    renderKardex();
    await waitFor(() => {
      // ENTRADA (50) + AJUSTE (5) = 55
      expect(screen.getByText('55')).toBeInTheDocument();
    });
  });

  it('calculates Total salidas summary card correctly', async () => {
    vi.mocked(productoInventarioService.getById).mockResolvedValue(mockProducto as never);
    vi.mocked(productoInventarioService.getKardex).mockResolvedValue(mockMovimientos as never[]);
    renderKardex();
    await waitFor(() => {
      // SALIDA (20)
      expect(screen.getByText('20')).toBeInTheDocument();
    });
  });

  it('shows empty message when no movements exist', async () => {
    vi.mocked(productoInventarioService.getById).mockResolvedValue(mockProducto as never);
    vi.mocked(productoInventarioService.getKardex).mockResolvedValue([]);
    renderKardex();
    await waitFor(() => {
      expect(screen.getByText(/no hay movimientos en el período/i)).toBeInTheDocument();
    });
  });

  it('renders the Ajuste action button', async () => {
    vi.mocked(productoInventarioService.getById).mockResolvedValue(mockProducto as never);
    vi.mocked(productoInventarioService.getKardex).mockResolvedValue(mockMovimientos as never[]);
    renderKardex();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /ajuste/i })).toBeInTheDocument();
    });
  });

  it('shows observation text in movement table', async () => {
    vi.mocked(productoInventarioService.getById).mockResolvedValue(mockProducto as never);
    vi.mocked(productoInventarioService.getKardex).mockResolvedValue(mockMovimientos as never[]);
    renderKardex();
    await waitFor(() => {
      expect(screen.getByText('Compra inicial')).toBeInTheDocument();
      expect(screen.getByText('Conteo físico')).toBeInTheDocument();
    });
  });
});
