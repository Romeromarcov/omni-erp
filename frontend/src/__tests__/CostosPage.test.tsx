import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
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
import CostosPage from '../pages/Costos/CostosPage';

const ordenApi = {
  id: 'op1',
  producto: 'p1',
  cantidad: '10',
  fecha_inicio: '2026-06-01',
  fecha_fin: null,
  estado: 'en_proceso',
  lista_materiales: null,
  ruta_produccion: null,
  referencia_externa: 'OF-001',
  observaciones: '',
};

const productoApi = { id_producto: 'p1', nombre_producto: 'Mesa de roble' };
const monedaApi = { id_moneda: 'm1', nombre: 'Dólar', codigo_iso: 'USD' };

const produccionApi = {
  id_costo_produccion: 'cp1',
  id_empresa: 'e1',
  id_orden_produccion: 'op1',
  tipo_costo: 'MATERIAL_DIRECTO',
  costo_unitario: '10.0000',
  cantidad: '5.0000',
  costo_total: '50.0000',
  id_moneda: 'm1',
  fecha_calculo: '2026-06-24T00:00:00Z',
  observaciones: 'nota',
  activo: true,
};

const estandarApi = {
  id_costo_estandar: 'ce1',
  id_empresa: 'e1',
  id_producto: 'p1',
  tipo_costo: 'MANO_OBRA_DIRECTA',
  costo_unitario_estandar: '12.0000',
  id_moneda: 'm1',
  fecha_vigencia_desde: '2026-06-01',
  fecha_vigencia_hasta: null,
  activo: true,
};

const variacionApi = {
  id_analisis_variacion: 'av1',
  id_empresa: 'e1',
  id_orden_produccion: 'op1',
  id_producto: 'p1',
  tipo_costo: 'OVERHEAD',
  costo_estandar: '50.0000',
  costo_real: '48.0000',
  variacion_cantidad: '0.0000',
  variacion_precio: '2.0000',
  variacion_total: '2.0000',
  porcentaje_variacion: '4.00',
  tipo_variacion: 'FAVORABLE',
  fecha_analisis: '2026-06-24T00:00:00Z',
  observaciones: null,
  activo: true,
};

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/inventario/productos')) return Promise.resolve([productoApi]);
    if (url.startsWith('/finanzas/monedas')) return Promise.resolve([monedaApi]);
    if (url.startsWith('/manufactura/ordenes-produccion'))
      return Promise.resolve({ count: 1, next: null, previous: null, results: [ordenApi] });
    if (url.startsWith('/costos/costos-produccion')) return Promise.resolve([produccionApi]);
    if (url.startsWith('/costos/costos-estandar-producto')) return Promise.resolve([estandarApi]);
    if (url.startsWith('/costos/analisis-variacion-costo')) return Promise.resolve([variacionApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CostosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const irAEstandar = () => fireEvent.click(screen.getByRole('tab', { name: 'Costo estándar' }));
const irAVariacion = () =>
  fireEvent.click(screen.getByRole('tab', { name: 'Análisis de variación' }));

describe('CostosPage — tab Costo real', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista costos de producción resolviendo la orden por referencia', async () => {
    renderPage();
    expect(await screen.findByText('OF-001')).toBeInTheDocument();
    expect(screen.getByText('Material Directo')).toBeInTheDocument();
  });

  it('valida la orden requerida al crear', async () => {
    renderPage();
    await screen.findByText('OF-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo real' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Seleccione la orden de producción/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('valida el costo total requerido al crear', async () => {
    renderPage();
    await screen.findByText('OF-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo real' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Orden de producción/));
    fireEvent.click(await screen.findByRole('option', { name: 'OF-001' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique el costo total/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un costo real con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValue({ id_costo_produccion: 'cp2' });
    renderPage();
    await screen.findByText('OF-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo real' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Orden de producción/));
    fireEvent.click(await screen.findByRole('option', { name: 'OF-001' }));
    fireEvent.change(within(dialog).getByLabelText(/Costo total/), {
      target: { value: '99.50' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/costos/costos-produccion/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_orden_produccion: 'op1',
          tipo_costo: 'MATERIAL_DIRECTO',
          costo_total: '99.50',
          costo_unitario: '0',
          cantidad: '0',
          observaciones: null,
          activo: true,
        }),
      ),
    );
  });

  it('edita un costo real enviando el payload por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_costo_produccion: 'cp1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Costo total/), {
      target: { value: '60.00' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/costos/costos-produccion/cp1/',
        expect.objectContaining({ costo_total: '60.00', id_orden_produccion: 'op1' }),
      ),
    );
  });

  it('elimina con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/costos/costos-produccion/cp1/'));
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('muestra error al fallar el guardado (mensajeDeError)', async () => {
    vi.mocked(post).mockRejectedValue(
      new Error(JSON.stringify({ costo_total: ['Inválido.'] })),
    );
    renderPage();
    await screen.findByText('OF-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo real' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Orden de producción/));
    fireEvent.click(await screen.findByRole('option', { name: 'OF-001' }));
    fireEvent.change(within(dialog).getByLabelText(/Costo total/), { target: { value: '1' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Inválido/)).toBeInTheDocument();
  });
});

describe('CostosPage — tab Costo estándar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista costos estándar resolviendo el producto', async () => {
    renderPage();
    irAEstandar();
    expect(await screen.findByText('Mesa de roble')).toBeInTheDocument();
    expect(screen.getByText('Mano de Obra Directa')).toBeInTheDocument();
  });

  it('valida producto, costo y vigencia desde al crear', async () => {
    renderPage();
    irAEstandar();
    await screen.findByText('Mesa de roble');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo estándar' }));
    const dialog = await screen.findByRole('dialog');

    // Sin producto.
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Seleccione el producto/)).toBeInTheDocument();

    // Con producto pero sin costo.
    fireEvent.mouseDown(within(dialog).getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: 'Mesa de roble' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Indique el costo unitario estándar/),
    ).toBeInTheDocument();

    // Con costo pero sin vigencia.
    fireEvent.change(within(dialog).getByLabelText(/Costo unitario estándar/), {
      target: { value: '15' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique la fecha de vigencia desde/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un costo estándar con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValue({ id_costo_estandar: 'ce2' });
    renderPage();
    irAEstandar();
    await screen.findByText('Mesa de roble');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo estándar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: 'Mesa de roble' }));
    fireEvent.change(within(dialog).getByLabelText(/Costo unitario estándar/), {
      target: { value: '15.00' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Vigencia desde/), {
      target: { value: '2026-07-01' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/costos/costos-estandar-producto/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_producto: 'p1',
          costo_unitario_estandar: '15.00',
          fecha_vigencia_desde: '2026-07-01',
          fecha_vigencia_hasta: null,
          activo: true,
        }),
      ),
    );
  });

  it('edita un costo estándar por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_costo_estandar: 'ce1' });
    renderPage();
    irAEstandar();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Costo unitario estándar/), {
      target: { value: '20.00' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/costos/costos-estandar-producto/ce1/',
        expect.objectContaining({ costo_unitario_estandar: '20.00', id_producto: 'p1' }),
      ),
    );
  });

  it('elimina con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    irAEstandar();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/costos/costos-estandar-producto/ce1/'),
    );
    confirmSpy.mockRestore();
  });

  it('muestra error al fallar el guardado', async () => {
    vi.mocked(post).mockRejectedValue(new Error('boom'));
    renderPage();
    irAEstandar();
    await screen.findByText('Mesa de roble');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo estándar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: 'Mesa de roble' }));
    fireEvent.change(within(dialog).getByLabelText(/Costo unitario estándar/), {
      target: { value: '15' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Vigencia desde/), {
      target: { value: '2026-07-01' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/boom/)).toBeInTheDocument();
  });
});

describe('CostosPage — tab Análisis de variación', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista variaciones mostrando el chip de resultado y el porcentaje', async () => {
    renderPage();
    irAVariacion();
    expect(await screen.findByText('FAVORABLE')).toBeInTheDocument();
    expect(screen.getByText('2.0000 (4.00%)')).toBeInTheDocument();
  });

  it('valida orden, producto y variación total al crear', async () => {
    renderPage();
    irAVariacion();
    await screen.findByText('FAVORABLE');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo análisis' }));
    const dialog = await screen.findByRole('dialog');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Seleccione la orden de producción/)).toBeInTheDocument();

    fireEvent.mouseDown(within(dialog).getByLabelText(/Orden de producción/));
    fireEvent.click(await screen.findByRole('option', { name: 'OF-001' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Seleccione el producto/)).toBeInTheDocument();

    fireEvent.mouseDown(within(dialog).getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: 'Mesa de roble' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique la variación total/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un análisis con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValue({ id_analisis_variacion: 'av2' });
    renderPage();
    irAVariacion();
    await screen.findByText('FAVORABLE');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo análisis' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Orden de producción/));
    fireEvent.click(await screen.findByRole('option', { name: 'OF-001' }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: 'Mesa de roble' }));
    fireEvent.change(within(dialog).getByLabelText(/Variación total/), {
      target: { value: '3.00' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/costos/analisis-variacion-costo/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_orden_produccion: 'op1',
          id_producto: 'p1',
          variacion_total: '3.00',
          tipo_variacion: 'NEUTRO',
          observaciones: null,
          activo: true,
        }),
      ),
    );
  });

  it('edita un análisis por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_analisis_variacion: 'av1' });
    renderPage();
    irAVariacion();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Variación total/), {
      target: { value: '5.00' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/costos/analisis-variacion-costo/av1/',
        expect.objectContaining({ variacion_total: '5.00', tipo_variacion: 'FAVORABLE' }),
      ),
    );
  });

  it('elimina con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    irAVariacion();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/costos/analisis-variacion-costo/av1/'),
    );
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    irAVariacion();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('muestra error al fallar la eliminación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockRejectedValue(new Error('en uso'));
    renderPage();
    irAVariacion();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(await screen.findByText(/en uso/)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it('crea un análisis rellenando todos los campos (onChange y checkbox)', async () => {
    vi.mocked(post).mockResolvedValue({ id_analisis_variacion: 'av9' });
    renderPage();
    irAVariacion();
    await screen.findByText('FAVORABLE');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo análisis' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Orden de producción/));
    fireEvent.click(await screen.findByRole('option', { name: 'OF-001' }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: 'Mesa de roble' }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/Tipo de costo/));
    fireEvent.click(await screen.findByRole('option', { name: 'Overhead' }));
    fireEvent.change(within(dialog).getByLabelText(/Costo estándar/), { target: { value: '100' } });
    fireEvent.change(within(dialog).getByLabelText(/Costo real/), { target: { value: '90' } });
    fireEvent.change(within(dialog).getByLabelText(/Variación cantidad/), { target: { value: '1' } });
    fireEvent.change(within(dialog).getByLabelText(/Variación precio/), { target: { value: '9' } });
    fireEvent.change(within(dialog).getByLabelText(/Variación total/), { target: { value: '10' } });
    fireEvent.change(within(dialog).getByLabelText(/Porcentaje de variación/), { target: { value: '10' } });
    fireEvent.mouseDown(within(dialog).getByLabelText('Resultado'));
    fireEvent.click(await screen.findByRole('option', { name: 'Desfavorable' }));
    fireEvent.change(within(dialog).getByLabelText(/Fecha de análisis/), { target: { value: '2026-06-26' } });
    fireEvent.change(within(dialog).getByLabelText(/Observaciones/), { target: { value: 'revisar overhead' } });
    fireEvent.click(within(dialog).getByRole('checkbox')); // activo -> false
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/costos/analisis-variacion-costo/',
        expect.objectContaining({
          tipo_costo: 'OVERHEAD',
          costo_estandar: '100',
          costo_real: '90',
          variacion_cantidad: '1',
          variacion_precio: '9',
          variacion_total: '10',
          porcentaje_variacion: '10',
          tipo_variacion: 'DESFAVORABLE',
          fecha_analisis: '2026-06-26',
          observaciones: 'revisar overhead',
          activo: false,
        }),
      ),
    );
  });

  it('precarga todos los campos al editar un análisis existente', async () => {
    vi.mocked(patch).mockResolvedValue({ id_analisis_variacion: 'av1' });
    renderPage();
    irAVariacion();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const dialog = await screen.findByRole('dialog');
    const costoReal = within(dialog).getByLabelText(/Costo real/) as HTMLInputElement;
    await waitFor(() => expect(costoReal.value).toBe('48.0000'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});

describe('CostosPage — campos y rutas de error adicionales', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('costo real: rellena todos los campos opcionales (onChange y checkbox)', async () => {
    vi.mocked(post).mockResolvedValue({ id_costo_produccion: 'cp9' });
    renderPage();
    await screen.findByText('OF-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo real' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Orden de producción/));
    fireEvent.click(await screen.findByRole('option', { name: 'OF-001' }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/Tipo de costo/));
    fireEvent.click(await screen.findByRole('option', { name: 'Overhead' }));
    fireEvent.change(within(dialog).getByLabelText(/Costo unitario/), { target: { value: '8' } });
    fireEvent.change(within(dialog).getByLabelText(/Cantidad/), { target: { value: '4' } });
    fireEvent.change(within(dialog).getByLabelText(/Costo total/), { target: { value: '32' } });
    fireEvent.change(within(dialog).getByLabelText(/Fecha de cálculo/), { target: { value: '2026-06-20' } });
    fireEvent.change(within(dialog).getByLabelText(/Observaciones/), { target: { value: 'extra' } });
    fireEvent.click(within(dialog).getByRole('checkbox')); // activo -> false
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/costos/costos-produccion/',
        expect.objectContaining({
          tipo_costo: 'OVERHEAD',
          costo_unitario: '8',
          cantidad: '4',
          costo_total: '32',
          fecha_calculo: '2026-06-20',
          observaciones: 'extra',
          activo: false,
        }),
      ),
    );
  });

  it('costo real: valida moneda requerida cuando no hay monedas precargadas', async () => {
    // Sin monedas, abrirCrear deja id_moneda vacío y se exige seleccionar.
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/inventario/productos')) return Promise.resolve([productoApi]);
      if (url.startsWith('/finanzas/monedas')) return Promise.resolve([]);
      if (url.startsWith('/manufactura/ordenes-produccion'))
        return Promise.resolve({ count: 1, next: null, previous: null, results: [ordenApi] });
      if (url.startsWith('/costos/costos-produccion')) return Promise.resolve([produccionApi]);
      return Promise.resolve([]);
    });
    renderPage();
    await screen.findByText('OF-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo real' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Orden de producción/));
    fireEvent.click(await screen.findByRole('option', { name: 'OF-001' }));
    fireEvent.change(within(dialog).getByLabelText(/Costo total/), { target: { value: '5' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Seleccione la moneda/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('costo real: cierra el diálogo con Cancelar y reporta error al eliminar', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockRejectedValue(new Error('costo en uso'));
    renderPage();
    await screen.findByText('OF-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo real' }));
    await screen.findByRole('dialog');
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }));
    expect(await screen.findByText(/costo en uso/)).toBeInTheDocument();
    // Cierra el alert.
    fireEvent.click(screen.getByLabelText('Close'));
    await waitFor(() => expect(screen.queryByText(/costo en uso/)).not.toBeInTheDocument());
    confirmSpy.mockRestore();
  });

  it('costo estándar: valida moneda requerida y rellena vigencia hasta', async () => {
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/inventario/productos')) return Promise.resolve([productoApi]);
      if (url.startsWith('/finanzas/monedas')) return Promise.resolve([]);
      if (url.startsWith('/manufactura/ordenes-produccion'))
        return Promise.resolve({ count: 0, next: null, previous: null, results: [] });
      if (url.startsWith('/costos/costos-estandar-producto')) return Promise.resolve([estandarApi]);
      return Promise.resolve([]);
    });
    renderPage();
    irAEstandar();
    await screen.findByText('Mesa de roble');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo estándar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: 'Mesa de roble' }));
    fireEvent.change(within(dialog).getByLabelText(/Costo unitario estándar/), { target: { value: '9' } });
    fireEvent.change(within(dialog).getByLabelText(/Vigencia desde/), { target: { value: '2026-07-01' } });
    fireEvent.change(within(dialog).getByLabelText(/Vigencia hasta/), { target: { value: '2026-12-31' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Seleccione la moneda/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('costo estándar: cambia tipo de costo, alterna activo y crea con vigencia hasta', async () => {
    vi.mocked(post).mockResolvedValue({ id_costo_estandar: 'ce9' });
    renderPage();
    irAEstandar();
    await screen.findByText('Mesa de roble');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo estándar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: 'Mesa de roble' }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/Tipo de costo/));
    fireEvent.click(await screen.findByRole('option', { name: 'Costos Indirectos' }));
    fireEvent.change(within(dialog).getByLabelText(/Costo unitario estándar/), { target: { value: '14' } });
    fireEvent.change(within(dialog).getByLabelText(/Vigencia desde/), { target: { value: '2026-07-01' } });
    fireEvent.change(within(dialog).getByLabelText(/Vigencia hasta/), { target: { value: '2026-09-30' } });
    fireEvent.click(within(dialog).getByRole('checkbox')); // activo -> false
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/costos/costos-estandar-producto/',
        expect.objectContaining({
          tipo_costo: 'COSTOS_INDIRECTOS',
          costo_unitario_estandar: '14',
          fecha_vigencia_hasta: '2026-09-30',
          activo: false,
        }),
      ),
    );
  });

  it('costo estándar: cancela el diálogo y reporta error al eliminar', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockRejectedValue(new Error('estandar en uso'));
    renderPage();
    irAEstandar();
    await screen.findByText('Mesa de roble');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo costo estándar' }));
    await screen.findByRole('dialog');
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }));
    expect(await screen.findByText(/estandar en uso/)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it('cancela el diálogo de análisis y reporta error al guardar', async () => {
    vi.mocked(post).mockRejectedValue(new Error('análisis inválido'));
    renderPage();
    irAVariacion();
    await screen.findByText('FAVORABLE');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo análisis' }));
    let dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Nuevo análisis' }));
    dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Orden de producción/));
    fireEvent.click(await screen.findByRole('option', { name: 'OF-001' }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: 'Mesa de roble' }));
    fireEvent.change(within(dialog).getByLabelText(/Variación total/), { target: { value: '1' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/análisis inválido/)).toBeInTheDocument();
  });
});
