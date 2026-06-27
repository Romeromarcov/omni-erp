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
import ComisionesPage from '../pages/Ventas/ComisionesPage';

const usuarioApi = { id: 'u1', username: 'jvendedor', email: '', first_name: '', last_name: '', is_active: true, es_superusuario_omni: false };
const categoriaApi = { id_categoria_producto: 'cat1', nombre_categoria: 'Bebidas' };

const esquemaApi = {
  id_esquema_comision: 'esq1',
  id_empresa: 'e1',
  vendedor: 'u1',
  vendedor_username: 'jvendedor',
  overrides_categoria: [],
  porcentaje_base: '5.0000',
  vigente_desde: '2026-01-01',
  vigente_hasta: null,
  activo: true,
  fecha_creacion: '2026-01-01',
};

const comisionApi = {
  id_comision_venta: 'k1',
  id_empresa: 'e1',
  vendedor: 'u1',
  vendedor_username: 'jvendedor',
  nota_venta: 'nv1',
  numero_nota: 'NV-001',
  esquema: 'esq1',
  id_moneda: 'm1',
  liquidada_por: null,
  base_comisionable: '100.0000',
  monto: '5.0000',
  estado: 'DEVENGADA',
  fecha_devengo: '2026-03-01',
  fecha_liquidacion: null,
};

const categoriaOverrideApi = {
  id_esquema_comision_categoria: 'c1',
  esquema: 'esq1',
  categoria: 'cat1',
  categoria_nombre: 'Bebidas',
  porcentaje: '8.0000',
};

const resumenApi = {
  resultados: [
    { vendedor: 'u1', vendedor_username: 'jvendedor', devengada: '5.0000', liquidada: '0', anulada: '0', cantidad: 1 },
  ],
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ComisionesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockGet(opts: { esquemas?: unknown[]; comisiones?: unknown[]; overrides?: unknown[]; resumen?: unknown } = {}) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/core/usuarios')) return Promise.resolve([usuarioApi]);
    if (url.startsWith('/inventario/categorias-producto')) return Promise.resolve([categoriaApi]);
    if (url.startsWith('/ventas/esquemas-comision-categorias')) return Promise.resolve(opts.overrides ?? []);
    if (url.startsWith('/ventas/esquemas-comision')) return Promise.resolve(opts.esquemas ?? [esquemaApi]);
    if (url.startsWith('/ventas/comisiones/resumen')) return Promise.resolve(opts.resumen ?? { resultados: [] });
    if (url.startsWith('/ventas/comisiones')) return Promise.resolve(opts.comisiones ?? []);
    return Promise.resolve([]);
  });
}

describe('ComisionesPage — Esquemas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet();
  });

  it('lista los esquemas con vendedor y porcentaje base', async () => {
    renderPage();
    expect(await screen.findByText('jvendedor')).toBeInTheDocument();
    expect(screen.getByText('5.0000%')).toBeInTheDocument();
  });

  it('valida vendedor y porcentaje requeridos al crear', async () => {
    renderPage();
    await screen.findByText('jvendedor');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo esquema' }));
    expect(await screen.findByText('Nuevo esquema', { selector: 'h2' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Seleccione el vendedor e indique el porcentaje/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un esquema con el payload correcto', async () => {
    vi.mocked(post).mockResolvedValue({ id_esquema_comision: 'esq2' });
    renderPage();
    await screen.findByText('jvendedor');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo esquema' }));
    fireEvent.mouseDown(await screen.findByLabelText(/Vendedor/));
    fireEvent.click(await screen.findByRole('option', { name: 'jvendedor' }));
    fireEvent.change(screen.getByLabelText(/Porcentaje base/), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/ventas/esquemas-comision/',
        expect.objectContaining({ vendedor: 'u1', porcentaje_base: '7', activo: true }),
      ),
    );
  });

  it('editar un esquema envía PATCH por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_esquema_comision: 'esq1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const pct = await screen.findByLabelText(/Porcentaje base/);
    fireEvent.change(pct, { target: { value: '6.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/ventas/esquemas-comision/esq1/',
        expect.objectContaining({ porcentaje_base: '6.5' }),
      ),
    );
  });

  it('eliminar pide confirmación y llama al servicio', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/ventas/esquemas-comision/esq1/'));
    confirmSpy.mockRestore();
  });

  it('muestra error al fallar el guardado (mensajeDeError)', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ porcentaje_base: ['Inválido.'] })));
    renderPage();
    await screen.findByText('jvendedor');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo esquema' }));
    fireEvent.mouseDown(await screen.findByLabelText(/Vendedor/));
    fireEvent.click(await screen.findByRole('option', { name: 'jvendedor' }));
    fireEvent.change(screen.getByLabelText(/Porcentaje base/), { target: { value: '999' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/porcentaje_base: Inválido\./)).toBeInTheDocument();
  });
});

describe('ComisionesPage — categorías inline (drawer)', () => {
  beforeEach(() => vi.clearAllMocks());

  async function abrirCategorias() {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Categorías' }));
    await screen.findByText(/Comisión por categoría/);
  }

  it('valida categoría y porcentaje requeridos', async () => {
    mockGet();
    await abrirCategorias();
    fireEvent.click(screen.getByRole('button', { name: 'Agregar override' }));
    expect(await screen.findByText(/Seleccione una categoría e indique el porcentaje/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un override con el payload correcto', async () => {
    mockGet();
    vi.mocked(post).mockResolvedValue({ id_esquema_comision_categoria: 'c-new' });
    await abrirCategorias();
    fireEvent.mouseDown(screen.getByLabelText(/Categoría/));
    fireEvent.click(await screen.findByRole('option', { name: 'Bebidas' }));
    fireEvent.change(screen.getByLabelText('Porcentaje'), { target: { value: '8' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar override' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/ventas/esquemas-comision-categorias/',
        expect.objectContaining({ esquema: 'esq1', categoria: 'cat1', porcentaje: '8' }),
      ),
    );
  });

  it('edita un override existente (precarga y hace PATCH)', async () => {
    mockGet({ overrides: [categoriaOverrideApi] });
    vi.mocked(patch).mockResolvedValue({ id_esquema_comision_categoria: 'c1' });
    await abrirCategorias();
    expect(await screen.findByText(/Bebidas · 8\.0000%/)).toBeInTheDocument();
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const pct = screen.getByLabelText('Porcentaje') as HTMLInputElement;
    await waitFor(() => expect(pct.value).toBe('8.0000'));
    fireEvent.change(pct, { target: { value: '9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar override' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/ventas/esquemas-comision-categorias/c1/',
        expect.objectContaining({ porcentaje: '9' }),
      ),
    );
  });

  it('elimina un override', async () => {
    mockGet({ overrides: [categoriaOverrideApi] });
    vi.mocked(del).mockResolvedValue(undefined);
    await abrirCategorias();
    await screen.findByText(/Bebidas/);
    const delButtons = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delButtons[delButtons.length - 1]);
    await waitFor(() => expect(del).toHaveBeenCalledWith('/ventas/esquemas-comision-categorias/c1/'));
  });

  it('cierra el drawer con el botón de cerrar', async () => {
    mockGet();
    await abrirCategorias();
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar detalle' }));
    await waitFor(() =>
      expect(screen.queryByText(/Comisión por categoría/)).not.toBeInTheDocument(),
    );
  });
});

describe('ComisionesPage — Comisiones devengadas', () => {
  beforeEach(() => vi.clearAllMocks());

  async function irADevengadas() {
    renderPage();
    await screen.findByText('jvendedor');
    fireEvent.click(screen.getByRole('tab', { name: 'Comisiones devengadas' }));
  }

  it('lista las comisiones devengadas con su estado', async () => {
    mockGet({ comisiones: [comisionApi] });
    await irADevengadas();
    const fila = (await screen.findByText('NV-001')).closest('tr') as HTMLElement;
    expect(within(fila).getByText('DEVENGADA')).toBeInTheDocument();
  });

  it('muestra mensaje vacío cuando no hay comisiones', async () => {
    mockGet({ comisiones: [] });
    await irADevengadas();
    expect(await screen.findByText(/Sin comisiones devengadas/)).toBeInTheDocument();
  });

  it('filtra por estado (recarga el querystring)', async () => {
    mockGet({ comisiones: [comisionApi] });
    await irADevengadas();
    await screen.findByText('NV-001');
    fireEvent.mouseDown(screen.getByLabelText(/Estado/));
    fireEvent.click(await screen.findByRole('option', { name: 'Liquidada' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/ventas/comisiones/?estado=LIQUIDADA'),
    );
  });

  it('muestra el panel de resumen por vendedor', async () => {
    mockGet({ comisiones: [comisionApi], resumen: resumenApi });
    await irADevengadas();
    await waitFor(() => expect(screen.getByText(/Liquidada: 0 · 1 comisiones/)).toBeInTheDocument());
  });

  it('valida vendedor y período al liquidar', async () => {
    mockGet({ comisiones: [comisionApi] });
    await irADevengadas();
    await screen.findByText('NV-001');
    fireEvent.click(screen.getByRole('button', { name: 'Liquidar' }));
    const dialog = await screen.findByRole('dialog');
    // vendedor precargado en blanco (no hay filtro), falta período
    fireEvent.click(within(dialog).getByRole('button', { name: 'Liquidar' }));
    expect(await screen.findByText(/Seleccione el vendedor y el período/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('liquida con fechas y muestra el resultado', async () => {
    mockGet({ comisiones: [comisionApi] });
    vi.mocked(post).mockResolvedValue({
      vendedor: 'u1',
      desde: '2026-01-01',
      hasta: '2026-06-30',
      liquidadas: 2,
      monto_total: '10.0000',
    });
    await irADevengadas();
    await screen.findByText('NV-001');
    fireEvent.click(screen.getByRole('button', { name: 'Liquidar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Vendedor/));
    fireEvent.click(await screen.findByRole('option', { name: 'jvendedor' }));
    fireEvent.change(within(dialog).getByLabelText(/Desde/), { target: { value: '2026-01-01' } });
    fireEvent.change(within(dialog).getByLabelText(/Hasta/), { target: { value: '2026-06-30' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Liquidar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/ventas/comisiones/liquidar/', {
        vendedor: 'u1',
        desde: '2026-01-01',
        hasta: '2026-06-30',
      }),
    );
    expect(await screen.findByText(/Se liquidaron 2 comisiones/)).toBeInTheDocument();
  });

  it('muestra error si la liquidación falla', async () => {
    mockGet({ comisiones: [comisionApi] });
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ error: 'desde > hasta' })));
    await irADevengadas();
    await screen.findByText('NV-001');
    fireEvent.click(screen.getByRole('button', { name: 'Liquidar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Vendedor/));
    fireEvent.click(await screen.findByRole('option', { name: 'jvendedor' }));
    fireEvent.change(within(dialog).getByLabelText(/Desde/), { target: { value: '2026-06-30' } });
    fireEvent.change(within(dialog).getByLabelText(/Hasta/), { target: { value: '2026-01-01' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Liquidar' }));
    expect(await screen.findByText(/desde > hasta/)).toBeInTheDocument();
  });
});
