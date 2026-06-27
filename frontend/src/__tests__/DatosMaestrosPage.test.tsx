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
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));

import { get, post, patch, del } from '../services/api';
import DatosMaestrosPage from '../pages/Manufactura/DatosMaestrosPage';

const bomApi = {
  id: 'b1',
  empresa: 'e1',
  producto_final: 'p1',
  nombre: 'Mesa BOM',
  descripcion: 'desc',
  referencia_externa: 'V1',
};
const componenteApi = {
  id_detalle_lista: 'd1',
  id_lista_materiales: 'b1',
  id_producto: 'p2',
  cantidad_requerida: '4.0000',
  id_unidad_medida: 'u1',
  es_opcional: false,
  observaciones: '',
};
const rutaApi = { id: 'r1', empresa: 'e1', nombre: 'Ruta mesa', descripcion: '', referencia_externa: 'R1' };
const pasoApi = {
  id_detalle_ruta: 'rp1',
  id_ruta_produccion: 'r1',
  id_operacion: 'op1',
  id_centro_trabajo: 'c1',
  numero_secuencia: 1,
  tiempo_preparacion_minutos: '5.00',
  tiempo_operacion_minutos: '30.00',
  observaciones: '',
};
const centroApi = {
  id_centro_trabajo: 'c1',
  id_empresa: 'e1',
  codigo_centro: 'CT-1',
  nombre_centro: 'Corte',
  descripcion: '',
  tipo_centro: 'MAQUINA',
  capacidad_horas_dia: '8.00',
  costo_hora: '12.0000',
  activo: true,
};
const operacionApi = {
  id_operacion: 'op1',
  id_empresa: 'e1',
  codigo_operacion: 'OP-1',
  nombre_operacion: 'Cortar',
  descripcion: '',
  tiempo_estandar_minutos: '15.00',
  activo: true,
};
const productoApi = { id_producto: 'p1', id_empresa: 'e1', nombre_producto: 'Producto A', sku: 'P-A' };
const productoComp = { id_producto: 'p2', id_empresa: 'e1', nombre_producto: 'Tornillo', sku: 'T-1' };
const unidadApi = { id_unidad_medida: 'u1', nombre: 'Unidad', abreviatura: 'und' };

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DatosMaestrosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockGet(
  opts: {
    boms?: unknown[];
    componentes?: unknown[];
    rutas?: unknown[];
    pasos?: unknown[];
    centros?: unknown[];
  } = {},
) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/inventario/productos')) return Promise.resolve([productoApi, productoComp]);
    if (url.startsWith('/inventario/unidades-medida')) return Promise.resolve([unidadApi]);
    if (url.startsWith('/manufactura/listas-materiales-detalle')) return Promise.resolve(opts.componentes ?? []);
    if (url.startsWith('/manufactura/listas-materiales')) return Promise.resolve(opts.boms ?? [bomApi]);
    if (url.startsWith('/manufactura/rutas-produccion-detalle')) return Promise.resolve(opts.pasos ?? []);
    if (url.startsWith('/manufactura/rutas-produccion')) return Promise.resolve(opts.rutas ?? [rutaApi]);
    if (url.startsWith('/manufactura/centros-trabajo')) return Promise.resolve(opts.centros ?? [centroApi]);
    if (url.startsWith('/manufactura/operaciones-produccion')) return Promise.resolve([operacionApi]);
    return Promise.resolve([]);
  });
}

describe('DatosMaestrosPage — Listas de Materiales', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet();
  });

  it('lista los BOM con su producto a fabricar', async () => {
    renderPage();
    expect(await screen.findByText('Mesa BOM')).toBeInTheDocument();
    expect(screen.getByText(/Producto A/)).toBeInTheDocument();
  });

  it('valida nombre y producto requeridos al crear', async () => {
    renderPage();
    await screen.findByText('Mesa BOM');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva lista de materiales' }));
    await screen.findByText('Nueva lista de materiales', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete el nombre y el producto/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un BOM con el payload correcto', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'b2' });
    renderPage();
    await screen.findByText('Mesa BOM');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva lista de materiales' }));
    fireEvent.change(await screen.findByLabelText(/Nombre/), { target: { value: 'Silla BOM' } });
    fireEvent.mouseDown(screen.getByLabelText(/Producto a fabricar/));
    fireEvent.click(await screen.findByRole('option', { name: /Producto A/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/manufactura/listas-materiales/',
        expect.objectContaining({ nombre: 'Silla BOM', producto_final: 'p1' }),
      ),
    );
  });

  it('editar un BOM hace PATCH por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id: 'b1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const nombre = await screen.findByLabelText(/Nombre/);
    fireEvent.change(nombre, { target: { value: 'Mesa BOM v2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/manufactura/listas-materiales/b1/',
        expect.objectContaining({ nombre: 'Mesa BOM v2' }),
      ),
    );
  });

  it('eliminar pide confirmación y llama al servicio', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/manufactura/listas-materiales/b1/'));
    confirmSpy.mockRestore();
  });

  it('muestra error al fallar el guardado', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ nombre: ['Ya existe.'] })));
    renderPage();
    await screen.findByText('Mesa BOM');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva lista de materiales' }));
    fireEvent.change(await screen.findByLabelText(/Nombre/), { target: { value: 'X' } });
    fireEvent.mouseDown(screen.getByLabelText(/Producto a fabricar/));
    fireEvent.click(await screen.findByRole('option', { name: /Producto A/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/nombre: Ya existe\./)).toBeInTheDocument();
  });
});

describe('DatosMaestrosPage — Componentes del BOM (drawer)', () => {
  beforeEach(() => vi.clearAllMocks());

  async function abrirComponentes() {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Componentes' }));
    await screen.findByText('Componentes del BOM');
  }

  it('valida producto, cantidad y unidad requeridos', async () => {
    mockGet();
    await abrirComponentes();
    fireEvent.click(screen.getByRole('button', { name: 'Agregar componente' }));
    expect(await screen.findByText(/Seleccione un producto, la cantidad y la unidad/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un componente con el payload correcto', async () => {
    mockGet();
    vi.mocked(post).mockResolvedValue({ id_detalle_lista: 'd-new' });
    await abrirComponentes();
    fireEvent.mouseDown(screen.getByLabelText('Componente'));
    fireEvent.click(await screen.findByRole('option', { name: /Tornillo/ }));
    fireEvent.change(screen.getByLabelText('Cantidad requerida'), { target: { value: '8' } });
    fireEvent.mouseDown(screen.getByLabelText(/Unidad/));
    fireEvent.click(await screen.findByRole('option', { name: /Unidad/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Agregar componente' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/manufactura/listas-materiales-detalle/',
        expect.objectContaining({
          id_lista_materiales: 'b1',
          id_producto: 'p2',
          cantidad_requerida: '8',
          id_unidad_medida: 'u1',
        }),
      ),
    );
  });

  it('edita un componente existente (precarga y PATCH)', async () => {
    mockGet({ componentes: [componenteApi] });
    vi.mocked(patch).mockResolvedValue({ id_detalle_lista: 'd1' });
    await abrirComponentes();
    expect(await screen.findByText(/Tornillo.*4\.0000/)).toBeInTheDocument();
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const cantidad = screen.getByLabelText('Cantidad requerida') as HTMLInputElement;
    await waitFor(() => expect(cantidad.value).toBe('4.0000'));
    fireEvent.change(cantidad, { target: { value: '6' } });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar componente' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/manufactura/listas-materiales-detalle/d1/',
        expect.objectContaining({ cantidad_requerida: '6' }),
      ),
    );
  });

  it('elimina un componente', async () => {
    mockGet({ componentes: [componenteApi] });
    vi.mocked(del).mockResolvedValue(undefined);
    await abrirComponentes();
    await screen.findByText(/Tornillo/);
    const delButtons = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delButtons[delButtons.length - 1]);
    await waitFor(() => expect(del).toHaveBeenCalledWith('/manufactura/listas-materiales-detalle/d1/'));
  });
});

describe('DatosMaestrosPage — Rutas de Producción', () => {
  beforeEach(() => vi.clearAllMocks());

  async function irARutas() {
    renderPage();
    fireEvent.click(await screen.findByRole('tab', { name: 'Rutas de Producción' }));
    await screen.findByText('Ruta mesa');
  }

  it('lista las rutas y crea una nueva', async () => {
    mockGet();
    vi.mocked(post).mockResolvedValue({ id: 'r2' });
    await irARutas();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva ruta de producción' }));
    fireEvent.change(await screen.findByLabelText(/Nombre/), { target: { value: 'Ruta silla' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/manufactura/rutas-produccion/',
        expect.objectContaining({ nombre: 'Ruta silla' }),
      ),
    );
  });

  it('valida nombre requerido al crear ruta', async () => {
    mockGet();
    await irARutas();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva ruta de producción' }));
    await screen.findByText('Nueva ruta de producción', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete el nombre de la ruta/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('agrega un paso con operación y centro de trabajo', async () => {
    mockGet();
    vi.mocked(post).mockResolvedValue({ id_detalle_ruta: 'rp-new' });
    await irARutas();
    fireEvent.click(screen.getByRole('button', { name: 'Pasos' }));
    await screen.findByText(/Pasos de la ruta/);
    fireEvent.mouseDown(screen.getByLabelText('Operación'));
    fireEvent.click(await screen.findByRole('option', { name: /Cortar/ }));
    fireEvent.mouseDown(screen.getByLabelText(/Centro de trabajo/));
    fireEvent.click(await screen.findByRole('option', { name: /Corte/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Agregar paso' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/manufactura/rutas-produccion-detalle/',
        expect.objectContaining({
          id_ruta_produccion: 'r1',
          id_operacion: 'op1',
          id_centro_trabajo: 'c1',
          numero_secuencia: 1,
        }),
      ),
    );
  });

  it('valida operación/centro requeridos en el paso', async () => {
    mockGet();
    await irARutas();
    fireEvent.click(screen.getByRole('button', { name: 'Pasos' }));
    await screen.findByText(/Pasos de la ruta/);
    fireEvent.click(screen.getByRole('button', { name: 'Agregar paso' }));
    expect(await screen.findByText(/Indique una secuencia válida/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('elimina un paso existente', async () => {
    mockGet({ pasos: [pasoApi] });
    vi.mocked(del).mockResolvedValue(undefined);
    await irARutas();
    fireEvent.click(screen.getByRole('button', { name: 'Pasos' }));
    await screen.findByText(/Cortar/);
    const delButtons = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delButtons[delButtons.length - 1]);
    await waitFor(() => expect(del).toHaveBeenCalledWith('/manufactura/rutas-produccion-detalle/rp1/'));
  });
});

describe('DatosMaestrosPage — Centros de Trabajo', () => {
  beforeEach(() => vi.clearAllMocks());

  async function irACentros() {
    renderPage();
    fireEvent.click(await screen.findByRole('tab', { name: 'Centros de Trabajo' }));
    await screen.findByText('Corte');
  }

  it('lista los centros y crea uno nuevo', async () => {
    mockGet();
    vi.mocked(post).mockResolvedValue({ id_centro_trabajo: 'c2' });
    await irACentros();
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo centro de trabajo' }));
    fireEvent.change(await screen.findByLabelText(/Código/), { target: { value: 'CT-2' } });
    fireEvent.change(screen.getByLabelText(/Nombre/), { target: { value: 'Pintura' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/manufactura/centros-trabajo/',
        expect.objectContaining({ codigo_centro: 'CT-2', nombre_centro: 'Pintura', tipo_centro: 'MAQUINA' }),
      ),
    );
  });

  it('valida código y nombre requeridos', async () => {
    mockGet();
    await irACentros();
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo centro de trabajo' }));
    await screen.findByText('Nuevo centro de trabajo', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete el código y el nombre/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('edita un centro (PATCH)', async () => {
    mockGet();
    vi.mocked(patch).mockResolvedValue({ id_centro_trabajo: 'c1' });
    await irACentros();
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    const nombre = await screen.findByLabelText(/^Nombre/);
    fireEvent.change(nombre, { target: { value: 'Corte CNC' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/manufactura/centros-trabajo/c1/',
        expect.objectContaining({ nombre_centro: 'Corte CNC' }),
      ),
    );
  });

  it('elimina un centro con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    await irACentros();
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/manufactura/centros-trabajo/c1/'));
    confirmSpy.mockRestore();
  });
});
