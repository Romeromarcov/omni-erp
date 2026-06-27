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
import InventarioMaestrosPage from '../pages/Inventario/InventarioMaestrosPage';

const productoApi = { id_producto: 'p1', id_empresa: 'e1', nombre_producto: 'Camisa', sku: 'CAM-1' };
const productoApi2 = { id_producto: 'p2', id_empresa: 'e1', nombre_producto: 'Pantalón', sku: 'PAN-1' };
const unidadApi = { id_unidad_medida: 'u1', nombre: 'Unidad', abreviatura: 'und' };
const unidadApi2 = { id_unidad_medida: 'u2', nombre: 'Docena', abreviatura: 'doc' };
const clienteApi = { id_cliente: 'c1', razon_social: 'Cliente Uno' };
const proveedorApi = { id_proveedor: 'pr1', razon_social: 'Proveedor Uno' };
const monedaApi = { id_moneda: 'm1', nombre: 'Dólar', codigo_iso: 'USD' };

const varianteApi = {
  id_variante: 'v1',
  id_producto: 'p1',
  codigo_variante: 'CAM-AZUL',
  sku: 'SKU-A',
  atributos_json: { color: 'azul' },
  activo: true,
};
const conversionApi = {
  id_conversion: 'co1',
  id_producto: 'p1',
  id_unidad_origen: 'u2',
  id_unidad_destino: 'u1',
  factor_conversion: '12.00000000',
  activo: true,
};
const consClienteApi = {
  id_stock_consignacion: 's1',
  id_cliente: 'c1',
  id_producto: 'p1',
  id_variante: null,
  cantidad_consignada: '10.0000',
  cantidad_vendida: '2.0000',
  cantidad_devuelta: '0.0000',
  fecha_consignacion: '2026-06-01',
  fecha_vencimiento: null,
  precio_unitario_consignacion: '5.0000',
  id_moneda: 'm1',
  estado: 'ACTIVA',
};
const consProvApi = {
  id_stock_consignacion: 'sp1',
  id_proveedor: 'pr1',
  id_producto: 'p1',
  id_variante: null,
  cantidad_recibida: '20.0000',
  cantidad_consumida: '3.0000',
  cantidad_devuelta: '0.0000',
  fecha_recepcion: '2026-06-01',
  fecha_vencimiento: null,
  costo_unitario_consignacion: '3.0000',
  id_moneda: 'm1',
  estado: 'ACTIVA',
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <InventarioMaestrosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockGet(
  opts: {
    variantes?: unknown[];
    conversiones?: unknown[];
    consCliente?: unknown[];
    consProv?: unknown[];
  } = {},
) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/inventario/productos')) return Promise.resolve([productoApi, productoApi2]);
    if (url.startsWith('/inventario/unidades-medida')) return Promise.resolve([unidadApi, unidadApi2]);
    if (url.startsWith('/inventario/variantes-producto')) return Promise.resolve(opts.variantes ?? [varianteApi]);
    if (url.startsWith('/inventario/conversiones-unidad-medida'))
      return Promise.resolve(opts.conversiones ?? [conversionApi]);
    if (url.startsWith('/inventario/stock-consignacion-cliente'))
      return Promise.resolve(opts.consCliente ?? [consClienteApi]);
    if (url.startsWith('/inventario/stock-consignacion-proveedor'))
      return Promise.resolve(opts.consProv ?? [consProvApi]);
    if (url.startsWith('/crm/clientes')) return Promise.resolve([clienteApi]);
    if (url.startsWith('/proveedores/proveedores')) return Promise.resolve([proveedorApi]);
    if (url.startsWith('/finanzas/monedas')) return Promise.resolve([monedaApi]);
    return Promise.resolve([]);
  });
}

describe('InventarioMaestrosPage — Variantes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet();
  });

  it('lista las variantes con su producto base', async () => {
    renderPage();
    expect(await screen.findByText('CAM-AZUL')).toBeInTheDocument();
    expect(screen.getByText(/Camisa/)).toBeInTheDocument();
  });

  it('valida producto base requerido al crear', async () => {
    renderPage();
    await screen.findByText('CAM-AZUL');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva variante' }));
    await screen.findByText('Nueva variante', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Seleccione el producto base/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('rechaza atributos JSON inválido', async () => {
    renderPage();
    await screen.findByText('CAM-AZUL');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva variante' }));
    fireEvent.mouseDown(screen.getByLabelText(/Producto base/));
    fireEvent.click(await screen.findByRole('option', { name: /Camisa/ }));
    fireEvent.change(screen.getByLabelText(/Atributos/), { target: { value: 'no-json' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/JSON válido/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una variante con el payload correcto', async () => {
    vi.mocked(post).mockResolvedValue({ id_variante: 'v2' });
    renderPage();
    await screen.findByText('CAM-AZUL');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva variante' }));
    fireEvent.mouseDown(screen.getByLabelText(/Producto base/));
    fireEvent.click(await screen.findByRole('option', { name: /Pantalón/ }));
    fireEvent.change(screen.getByLabelText(/Código variante/), { target: { value: 'PAN-V' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/inventario/variantes-producto/',
        expect.objectContaining({ id_producto: 'p2', codigo_variante: 'PAN-V' }),
      ),
    );
  });

  it('editar una variante hace PATCH por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_variante: 'v1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const sku = await screen.findByLabelText(/SKU/);
    fireEvent.change(sku, { target: { value: 'SKU-Z' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/inventario/variantes-producto/v1/',
        expect.objectContaining({ sku: 'SKU-Z' }),
      ),
    );
  });

  it('elimina una variante con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/inventario/variantes-producto/v1/'));
    confirmSpy.mockRestore();
  });

  it('filtra por producto', async () => {
    renderPage();
    await screen.findByText('CAM-AZUL');
    fireEvent.mouseDown(screen.getByLabelText(/Filtrar por producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Pantalón/ }));
    await waitFor(() => expect(get).toHaveBeenCalledWith('/inventario/variantes-producto/'));
  });

  it('muestra error al fallar el guardado', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ sku: ['Ya existe.'] })));
    renderPage();
    await screen.findByText('CAM-AZUL');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva variante' }));
    fireEvent.mouseDown(screen.getByLabelText(/Producto base/));
    fireEvent.click(await screen.findByRole('option', { name: /Camisa/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/sku: Ya existe\./)).toBeInTheDocument();
  });
});

describe('InventarioMaestrosPage — Conversiones UM', () => {
  beforeEach(() => vi.clearAllMocks());

  async function irAConversiones() {
    mockGet();
    renderPage();
    fireEvent.click(await screen.findByRole('tab', { name: 'Conversiones UM' }));
    await screen.findByText(/Docena/);
  }

  it('lista las conversiones', async () => {
    await irAConversiones();
    expect(screen.getByText('12.00000000')).toBeInTheDocument();
  });

  it('valida campos requeridos', async () => {
    await irAConversiones();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva conversión' }));
    await screen.findByText('Nueva conversión', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete el producto, ambas unidades/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('rechaza unidades origen y destino iguales', async () => {
    await irAConversiones();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva conversión' }));
    fireEvent.mouseDown(screen.getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Camisa/ }));
    fireEvent.mouseDown(screen.getByLabelText('Unidad origen'));
    fireEvent.click(await screen.findByRole('option', { name: /Unidad \(und\)/ }));
    fireEvent.mouseDown(screen.getByLabelText('Unidad destino'));
    fireEvent.click(await screen.findByRole('option', { name: /Unidad \(und\)/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/deben ser distintas/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una conversión con el payload correcto', async () => {
    vi.mocked(post).mockResolvedValue({ id_conversion: 'co2' });
    await irAConversiones();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva conversión' }));
    fireEvent.mouseDown(screen.getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Camisa/ }));
    fireEvent.mouseDown(screen.getByLabelText('Unidad origen'));
    fireEvent.click(await screen.findByRole('option', { name: /Docena/ }));
    fireEvent.mouseDown(screen.getByLabelText('Unidad destino'));
    fireEvent.click(await screen.findByRole('option', { name: /Unidad \(und\)/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/inventario/conversiones-unidad-medida/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_producto: 'p1',
          id_unidad_origen: 'u2',
          id_unidad_destino: 'u1',
        }),
      ),
    );
  });

  it('elimina una conversión', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    await irAConversiones();
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/inventario/conversiones-unidad-medida/co1/'));
    confirmSpy.mockRestore();
  });
});

describe('InventarioMaestrosPage — Consignación Cliente', () => {
  beforeEach(() => vi.clearAllMocks());

  async function irAConsCliente() {
    mockGet();
    renderPage();
    fireEvent.click(await screen.findByRole('tab', { name: 'Consignación Cliente' }));
    await screen.findByText('Cliente Uno');
  }

  it('lista los saldos con estado', async () => {
    await irAConsCliente();
    expect(screen.getByText('ACTIVA')).toBeInTheDocument();
  });

  it('valida campos requeridos al crear', async () => {
    await irAConsCliente();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva consignación' }));
    await screen.findByText('Nueva consignación a cliente', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete cliente, producto, moneda y fecha/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una consignación a cliente con el payload correcto', async () => {
    vi.mocked(post).mockResolvedValue({ id_stock_consignacion: 's2' });
    await irAConsCliente();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva consignación' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/^Cliente/));
    fireEvent.click(await screen.findByRole('option', { name: /Cliente Uno/ }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/^Producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Camisa/ }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/^Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD/ }));
    fireEvent.change(within(dialog).getByLabelText(/Fecha consignación/), {
      target: { value: '2026-06-27' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/inventario/stock-consignacion-cliente/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_cliente: 'c1',
          id_producto: 'p1',
          id_moneda: 'm1',
          fecha_consignacion: '2026-06-27',
          estado: 'ACTIVA',
        }),
      ),
    );
  });

  it('filtra por estado', async () => {
    await irAConsCliente();
    fireEvent.mouseDown(screen.getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'CERRADA' }));
    await waitFor(() => expect(get).toHaveBeenCalledWith('/inventario/stock-consignacion-cliente/'));
  });

  it('elimina un saldo', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    await irAConsCliente();
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/inventario/stock-consignacion-cliente/s1/'));
    confirmSpy.mockRestore();
  });
});

describe('InventarioMaestrosPage — Consignación Proveedor', () => {
  beforeEach(() => vi.clearAllMocks());

  async function irAConsProv() {
    mockGet();
    renderPage();
    fireEvent.click(await screen.findByRole('tab', { name: 'Consignación Proveedor' }));
    await screen.findByText('Proveedor Uno');
  }

  it('lista los saldos de proveedores', async () => {
    await irAConsProv();
    expect(screen.getByText('20.0000')).toBeInTheDocument();
  });

  it('valida campos requeridos al crear', async () => {
    await irAConsProv();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva consignación' }));
    await screen.findByText('Nueva consignación de proveedor', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete proveedor, producto, moneda y fecha/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una consignación de proveedor con el payload correcto', async () => {
    vi.mocked(post).mockResolvedValue({ id_stock_consignacion: 'sp2' });
    await irAConsProv();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva consignación' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/^Proveedor/));
    fireEvent.click(await screen.findByRole('option', { name: /Proveedor Uno/ }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/^Producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Camisa/ }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/^Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD/ }));
    fireEvent.change(within(dialog).getByLabelText(/Fecha recepción/), {
      target: { value: '2026-06-27' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/inventario/stock-consignacion-proveedor/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_proveedor: 'pr1',
          id_producto: 'p1',
          id_moneda: 'm1',
          fecha_recepcion: '2026-06-27',
          estado: 'ACTIVA',
        }),
      ),
    );
  });

  it('edita un saldo (PATCH)', async () => {
    vi.mocked(patch).mockResolvedValue({ id_stock_consignacion: 'sp1' });
    await irAConsProv();
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Cantidad consumida'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/inventario/stock-consignacion-proveedor/sp1/',
        expect.objectContaining({ cantidad_consumida: '5' }),
      ),
    );
  });
});
