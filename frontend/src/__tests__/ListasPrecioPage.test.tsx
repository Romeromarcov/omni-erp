import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  postForm: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));

import { get, post, patch, del, postForm } from '../services/api';
import ListasPrecioPage from '../pages/Ventas/ListasPrecioPage';

const listaApi = {
  id_lista: 'l1',
  id_empresa: 'e1',
  id_moneda: 'm1',
  nombre: 'Mayoreo',
  codigo: 'MAYOREO',
  es_referencia: false,
  activo: true,
  fecha_creacion: '2026-01-01',
};

const monedaApi = { id_moneda: 'm1', nombre: 'Bolívar', codigo_iso: 'VES' };
const productoApi = { id_producto: 'p1', id_empresa: 'e1', nombre_producto: 'Producto A', sku: 'P-A' };

const detalleApi = {
  id_detalle: 'd1',
  id_lista: 'l1',
  id_producto: 'p1',
  precio: '15.5000',
  precio_minimo: '12.0000',
  vigente_desde: null,
  vigente_hasta: null,
  activo: true,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ListasPrecioPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockGet(opts: { listas?: unknown[]; detalles?: unknown[] } = {}) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/finanzas/monedas')) return Promise.resolve([monedaApi]);
    if (url.startsWith('/inventario/productos')) return Promise.resolve([productoApi]);
    if (url.startsWith('/ventas/detalles-precio')) return Promise.resolve(opts.detalles ?? []);
    if (url.startsWith('/ventas/listas-precio')) return Promise.resolve(opts.listas ?? [listaApi]);
    return Promise.resolve([]);
  });
}

describe('ListasPrecioPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet();
  });

  it('lista las listas de precio con su código y nombre', async () => {
    renderPage();
    expect(await screen.findByText('Mayoreo')).toBeInTheDocument();
    expect(screen.getByText('MAYOREO')).toBeInTheDocument();
  });

  it('valida nombre, código y moneda requeridos al crear', async () => {
    renderPage();
    await screen.findByText('Mayoreo');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva lista' }));
    expect(await screen.findByText('Nueva lista de precios', { selector: 'h2' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete el nombre, el código y la moneda/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una lista de precios con el payload correcto', async () => {
    vi.mocked(post).mockResolvedValue({ id_lista: 'l2' });
    renderPage();
    await screen.findByText('Mayoreo');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva lista' }));
    fireEvent.change(await screen.findByLabelText(/Nombre/), { target: { value: 'Detal' } });
    fireEvent.change(screen.getByLabelText(/Código/), { target: { value: 'DETAL' } });
    fireEvent.mouseDown(screen.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /VES/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/ventas/listas-precio/',
        expect.objectContaining({
          nombre: 'Detal',
          codigo: 'DETAL',
          id_moneda: 'm1',
          es_referencia: false,
          activo: true,
        }),
      ),
    );
  });

  it('editar una lista envía PATCH por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_lista: 'l1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const nombre = await screen.findByLabelText(/Nombre/);
    fireEvent.change(nombre, { target: { value: 'Mayoreo Editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/ventas/listas-precio/l1/',
        expect.objectContaining({ nombre: 'Mayoreo Editado', codigo: 'MAYOREO' }),
      ),
    );
  });

  it('eliminar pide confirmación y llama al servicio', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/ventas/listas-precio/l1/'));
    confirmSpy.mockRestore();
  });

  it('no elimina si el usuario cancela', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('muestra error al fallar el guardado (mensajeDeError)', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ codigo: ['Ya existe.'] })));
    renderPage();
    await screen.findByText('Mayoreo');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva lista' }));
    fireEvent.change(await screen.findByLabelText(/Nombre/), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText(/Código/), { target: { value: 'X' } });
    fireEvent.mouseDown(screen.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /VES/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/codigo: Ya existe\./)).toBeInTheDocument();
  });

  it('cierra el diálogo con Cancelar', async () => {
    renderPage();
    await screen.findByText('Mayoreo');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva lista' }));
    await screen.findByText('Nueva lista de precios', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await waitFor(() =>
      expect(screen.queryByText('Nueva lista de precios', { selector: 'h2' })).not.toBeInTheDocument(),
    );
  });
});

// ── Drawer de precios (detalles): CRUD inline + importar CSV ───────────────────

async function abrirPrecios() {
  renderPage();
  fireEvent.click(await screen.findByRole('button', { name: 'Precios' }));
  await screen.findByText('Precios por producto');
}

describe('ListasPrecioPage — detalles (precios)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('valida producto y precio requeridos', async () => {
    mockGet();
    await abrirPrecios();
    fireEvent.click(screen.getByRole('button', { name: 'Agregar precio' }));
    expect(await screen.findByText(/Seleccione un producto e indique el precio/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un precio con el payload correcto', async () => {
    mockGet();
    vi.mocked(post).mockResolvedValue({ id_detalle: 'd-new' });
    await abrirPrecios();
    fireEvent.mouseDown(screen.getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Producto A/ }));
    fireEvent.change(screen.getByLabelText('Precio'), { target: { value: '20.00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar precio' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/ventas/detalles-precio/',
        expect.objectContaining({
          id_lista: 'l1',
          id_producto: 'p1',
          precio: '20.00',
          precio_minimo: '0',
          activo: true,
        }),
      ),
    );
  });

  it('edita un precio existente (precarga y hace PATCH)', async () => {
    mockGet({ detalles: [detalleApi] });
    vi.mocked(patch).mockResolvedValue({ id_detalle: 'd1' });
    await abrirPrecios();
    expect(await screen.findByText(/Producto A.*15\.5000/)).toBeInTheDocument();
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const precio = screen.getByLabelText('Precio') as HTMLInputElement;
    await waitFor(() => expect(precio.value).toBe('15.5000'));
    fireEvent.change(precio, { target: { value: '18.00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar precio' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/ventas/detalles-precio/d1/',
        expect.objectContaining({ precio: '18.00' }),
      ),
    );
  });

  it('elimina un precio', async () => {
    mockGet({ detalles: [detalleApi] });
    vi.mocked(del).mockResolvedValue(undefined);
    await abrirPrecios();
    await screen.findByText(/Producto A/);
    const delButtons = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delButtons[delButtons.length - 1]);
    await waitFor(() => expect(del).toHaveBeenCalledWith('/ventas/detalles-precio/d1/'));
  });

  it('cancela la edición de un precio', async () => {
    mockGet({ detalles: [detalleApi] });
    await abrirPrecios();
    await screen.findByText(/Producto A/);
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const cancelar = await screen.findByRole('button', { name: 'Cancelar' });
    fireEvent.click(cancelar);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Agregar precio' })).toBeInTheDocument(),
    );
  });

  it('importa un CSV con archivo mock y muestra el resultado', async () => {
    mockGet();
    vi.mocked(postForm).mockResolvedValue({
      lista: 'Mayoreo',
      creados: 3,
      actualizados: 1,
      errores: [],
      total_errores: 0,
    });
    await abrirPrecios();
    const input = screen.getByLabelText('Importar CSV', { selector: 'input' });
    const file = new File(['codigo_producto,precio\nP-A,10'], 'precios.csv', { type: 'text/csv' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(postForm).toHaveBeenCalledTimes(1));
    expect(vi.mocked(postForm).mock.calls[0][0]).toBe('/ventas/listas-precio/l1/importar-masivo/');
    expect(await screen.findByText(/3 creados, 1 actualizados/)).toBeInTheDocument();
  });

  it('muestra errores de filas tras importar un CSV con problemas', async () => {
    mockGet();
    vi.mocked(postForm).mockResolvedValue({
      lista: 'Mayoreo',
      creados: 0,
      actualizados: 0,
      errores: [{ fila: 2, error: "Producto 'X' no encontrado" }],
      total_errores: 1,
    });
    await abrirPrecios();
    const input = screen.getByLabelText('Importar CSV', { selector: 'input' });
    const file = new File(['x'], 'mal.csv', { type: 'text/csv' });
    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByText(/Fila 2:/)).toBeInTheDocument();
  });

  it('muestra error si la importación falla', async () => {
    mockGet();
    vi.mocked(postForm).mockRejectedValue(new Error(JSON.stringify({ error: 'CSV inválido.' })));
    await abrirPrecios();
    const input = screen.getByLabelText('Importar CSV', { selector: 'input' });
    const file = new File(['x'], 'mal.csv', { type: 'text/csv' });
    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByText(/CSV inválido\./)).toBeInTheDocument();
  });

  it('cierra el drawer con el botón de cerrar', async () => {
    mockGet();
    await abrirPrecios();
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar detalle' }));
    await waitFor(() =>
      expect(screen.queryByText('Precios por producto')).not.toBeInTheDocument(),
    );
  });
});
