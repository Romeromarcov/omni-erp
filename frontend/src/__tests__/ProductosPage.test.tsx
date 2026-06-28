import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));
vi.mock('../services/monedas', () => ({ fetchMonedas: vi.fn() }));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));

import { get, post, patch, del } from '../services/api';
import {
  productoInventarioService,
  categoriasProductoService,
  unidadesMedidaService,
} from '../services/inventarioService';
import { fetchMonedas } from '../services/monedas';
import ProductosPage from '../pages/Inventario/ProductosPage';

const productoApi = {
  id_producto: 'prod-1',
  id_empresa: 'e1',
  nombre_producto: 'Tornillo',
  sku: 'TOR-001',
  descripcion: null,
  tipo_producto: 'PRODUCTO_FISICO',
  maneja_lotes: false,
  maneja_seriales: false,
  costo_promedio: '5.0000',
  metodo_valoracion: 'PROMEDIO',
  precio_venta_sugerido: '9.0000',
  punto_reorden: '10.0000',
  id_categoria: 'cat-1',
  id_unidad_medida_base: 'um-1',
  id_moneda_precio: 'mon-1',
  nombre_categoria: 'Ferretería',
  nombre_unidad_medida: 'Unidad',
  activo: true,
};

describe('productoInventarioService CRUD escritura', () => {
  beforeEach(() => vi.clearAllMocks());

  const payload = {
    id_empresa: 'e1',
    nombre_producto: 'Tuerca',
    sku: 'TUE-1',
    id_categoria: 'cat-1',
    id_unidad_medida_base: 'um-1',
    tipo_producto: 'PRODUCTO_FISICO',
    maneja_lotes: false,
    maneja_seriales: false,
    costo_promedio: '1.50',
    precio_venta_sugerido: '3.00',
    punto_reorden: null,
    metodo_valoracion: 'FIFO' as const,
    id_moneda_precio: 'mon-1',
  };

  it('create postea al endpoint de productos', async () => {
    vi.mocked(post).mockResolvedValue({ id_producto: 'p2' });
    await productoInventarioService.create(payload);
    expect(post).toHaveBeenCalledWith('/inventario/productos/', payload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_producto: 'p2' });
    await productoInventarioService.update('p2', payload);
    expect(patch).toHaveBeenCalledWith('/inventario/productos/p2/', payload);
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    await productoInventarioService.remove('p2');
    expect(del).toHaveBeenCalledWith('/inventario/productos/p2/');
  });

  it('catálogos de categorías y unidades usan sus endpoints', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_categoria_producto: 'c1' }] });
    expect(await categoriasProductoService.getAll()).toEqual([{ id_categoria_producto: 'c1' }]);
    // getAll recorre páginas: la primera petición incluye page=1.
    expect(get).toHaveBeenCalledWith('/inventario/categorias-producto/?page=1');

    vi.mocked(get).mockResolvedValueOnce([{ id_unidad_medida: 'u1' }]);
    expect(await unidadesMedidaService.getAll()).toEqual([{ id_unidad_medida: 'u1' }]);
    expect(get).toHaveBeenCalledWith('/inventario/unidades-medida/?page=1');
  });
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ProductosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProductosPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/inventario/categorias-producto')) {
        return Promise.resolve([{ id_categoria_producto: 'cat-1', nombre_categoria: 'Ferretería' }]);
      }
      if (url.startsWith('/inventario/unidades-medida')) {
        return Promise.resolve([{ id_unidad_medida: 'um-1', nombre: 'Unidad', abreviatura: 'UN' }]);
      }
      if (url.startsWith('/inventario/productos')) {
        return Promise.resolve([productoApi]);
      }
      return Promise.resolve([]);
    });
    vi.mocked(fetchMonedas).mockResolvedValue([
      { id_moneda: 'mon-1', nombre: 'Dólar', codigo_iso: 'USD' },
    ]);
  });

  it('lista los productos con su método de valoración', async () => {
    renderPage();
    expect(await screen.findByText('Tornillo')).toBeInTheDocument();
    expect(screen.getByText('Ferretería')).toBeInTheDocument();
    expect(screen.getByText('PROMEDIO')).toBeInTheDocument();
  });

  it('valida campos requeridos al crear', async () => {
    renderPage();
    await screen.findByText('Tornillo');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo producto' }));
    expect(await screen.findByText('Nuevo producto', { selector: 'h2' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete nombre/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('editar un producto envía el payload con whitelist y montos como string', async () => {
    vi.mocked(patch).mockResolvedValue({ id_producto: 'prod-1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const nombre = await screen.findByLabelText(/Nombre/);
    fireEvent.change(nombre, { target: { value: 'Tornillo XL' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/inventario/productos/prod-1/',
        expect.objectContaining({
          id_empresa: 'e1',
          nombre_producto: 'Tornillo XL',
          metodo_valoracion: 'PROMEDIO',
          costo_promedio: '5.0000',
          id_moneda_precio: 'mon-1',
        }),
      ),
    );
  });

  it('eliminar un producto llama al servicio', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/inventario/productos/prod-1/'));
  });
});
