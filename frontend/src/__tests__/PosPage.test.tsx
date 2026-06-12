/**
 * Sub-fase 1.G — POS de mostrador: flujos críticos.
 *  - agregar al carrito por búsqueda (click) y por "scan" (SKU + Enter);
 *  - totales exactos con decimal.js;
 *  - cobro mixto multimoneda con vuelto e Idempotency-Key por pago;
 *  - error del backend visible (crear venta y registrar pagos);
 *  - sesión de caja requerida (ofrece abrirla y llama abrir-sesion).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

const SESION = {
  id_sesion: 'ses-1',
  usuario: { id: 1, username: 'cajero', first_name: 'Caja', last_name: 'Uno' },
  caja_fisica_principal: {
    id_caja: 'caja-1',
    nombre: 'Caja Mostrador',
    sucursal: {
      id_sucursal: 'suc-1',
      nombre: 'Principal',
      empresa: { id_empresa: 'emp-1', nombre: 'Distribuidora Demo' },
    },
  },
  estado: 'ABIERTA',
  fecha_apertura: '2026-06-12T08:00:00Z',
};

const getSesionActivaMock = vi.fn();
vi.mock('../services/sesionService', () => ({
  getSesionActiva: (...a: unknown[]) => getSesionActivaMock(...a),
}));

vi.mock('../services/productosService', () => ({
  fetchProductos: vi.fn().mockResolvedValue([
    { id_producto: 'p1', nombre_producto: 'Harina PAN', sku: 'HAR001', precio_venta_sugerido: 1.1 },
    { id_producto: 'p2', nombre_producto: 'Aceite Vatel', sku: 'ACE002', precio_venta_sugerido: 3.5 },
  ]),
}));

vi.mock('../services/metodosPagoEmpresaActiva', () => ({
  fetchMetodosPagoEmpresaActivos: vi.fn().mockResolvedValue([
    { id: 'met-efe', nombre_metodo: 'Efectivo', monedas: [] },
    { id: 'met-pm', nombre_metodo: 'Pago Móvil', monedas: ['mon-ves'] },
  ]),
}));

vi.mock('../services/monedasEmpresaActiva', () => ({
  fetchMonedasEmpresaActivas: vi.fn().mockResolvedValue([
    { id_moneda: 'mon-ves', nombre: 'Bolívar', codigo_iso: 'VES' },
    { id_moneda: 'mon-usd', nombre: 'Dólar', codigo_iso: 'USD' },
  ]),
}));

vi.mock('../services/tasaBCV', () => ({
  fetchTasaBCV: vi.fn().mockResolvedValue({ moneda_origen: 'USD', moneda_destino: 'VES', tasa: 40, fecha: '2026-06-12' }),
}));

vi.mock('../services/clientesService', () => ({
  buscarClientes: vi.fn().mockResolvedValue([{ id_cliente: 'cli-cf', razon_social: 'Consumidor Final' }]),
  crearClienteConEmpresa: vi.fn().mockResolvedValue({ id_cliente: 'cli-nuevo' }),
}));

const createNotaMock = vi.fn();
vi.mock('../services/ventas', () => ({
  notaVentaService: { create: (...a: unknown[]) => createNotaMock(...a) },
}));

const createPagoDocumentoMock = vi.fn();
vi.mock('../services/pagosService', () => ({
  pagosService: { createPagoDocumento: (...a: unknown[]) => createPagoDocumentoMock(...a) },
}));

const getCajasFisicasMock = vi.fn();
const abrirSesionMock = vi.fn();
vi.mock('../services/cajasFisicasService', () => ({
  cajasFisicasService: {
    getCajasFisicas: (...a: unknown[]) => getCajasFisicasMock(...a),
    abrirSesion: (...a: unknown[]) => abrirSesionMock(...a),
  },
}));

import PosPage from '../pages/Ventas/POS/PosPage';

function renderPos() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/pos']}>
        <PosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem('id_empresa', 'emp-1');
  getSesionActivaMock.mockResolvedValue(SESION);
  createNotaMock.mockResolvedValue({
    id_nota_venta: 'nv-1',
    numero_nota_venta: 'NV-0001',
    subtotal: 3.3,
    monto_impuesto: 0.53,
    monto_total: 3.83,
  });
  createPagoDocumentoMock.mockResolvedValue({});
  getCajasFisicasMock.mockResolvedValue({ results: [{ id_caja_fisica: 'cf-1', nombre: 'Caja Mostrador', sucursal_nombre: 'Principal' }], count: 1 });
  abrirSesionMock.mockResolvedValue({ mensaje: 'ok', sesion: { id_sesion: 'ses-1', estado: 'ABIERTA', fecha_apertura: '', usuario: 'cajero' } });
});

async function agregarHarinaPorScan(veces = 1) {
  const input = screen.getByTestId('pos-busqueda');
  for (let i = 0; i < veces; i++) {
    fireEvent.change(input, { target: { value: 'HAR001' } });
    fireEvent.keyDown(input, { key: 'Enter' });
  }
}

describe('PosPage', () => {
  it('agrega productos al carrito por búsqueda incremental + click', async () => {
    renderPos();
    await screen.findByText('Harina PAN');

    // Búsqueda incremental: filtra la grilla.
    fireEvent.change(screen.getByTestId('pos-busqueda'), { target: { value: 'aceite' } });
    const grilla = screen.getByTestId('pos-grilla-productos');
    expect(within(grilla).queryByText('Harina PAN')).not.toBeInTheDocument();

    fireEvent.click(within(grilla).getByText('Aceite Vatel'));
    const carrito = screen.getByTestId('pos-carrito');
    expect(within(carrito).getByText('Aceite Vatel')).toBeInTheDocument();
    expect(screen.getByTestId('pos-subtotal').textContent).toContain('3.50');
  });

  it('agrega por "scan" (SKU exacto + Enter), acumula cantidad y limpia el input', async () => {
    renderPos();
    await screen.findByText('Harina PAN');

    await agregarHarinaPorScan(3);
    const input = screen.getByTestId('pos-busqueda') as HTMLInputElement;
    expect(input.value).toBe('');
    // Totales exactos con decimal.js: 3 × 1.1 = 3.30 (no 3.3000000000000003).
    expect(screen.getByTestId('pos-linea-total-p1').textContent).toBe('3.30');
    expect(screen.getByTestId('pos-subtotal').textContent).toContain('3.30');
  });

  it('muestra aviso si el código escaneado no tiene coincidencia exacta', async () => {
    renderPos();
    await screen.findByText('Harina PAN');
    const input = screen.getByTestId('pos-busqueda');
    fireEvent.change(input, { target: { value: 'NOEXISTE' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getByTestId('pos-scan-error').textContent).toContain('NOEXISTE');
  });

  it('permite editar cantidades en el carrito y recalcula con decimal.js', async () => {
    renderPos();
    await screen.findByText('Harina PAN');
    await agregarHarinaPorScan();
    fireEvent.change(screen.getByLabelText('Cantidad Harina PAN'), { target: { value: '5' } });
    expect(screen.getByTestId('pos-linea-total-p1').textContent).toBe('5.50');
    fireEvent.click(screen.getByLabelText('Quitar Harina PAN'));
    expect(screen.getByTestId('pos-subtotal').textContent).toContain('0.00');
  });

  it('cobro mixto multimoneda: usa el total con IVA del backend, calcula vuelto y registra cada pago con Idempotency-Key', async () => {
    renderPos();
    await screen.findByText('Harina PAN');
    await agregarHarinaPorScan(3); // subtotal 3.30

    fireEvent.click(screen.getByTestId('pos-cobrar'));
    // Total e IVA según el backend (nota de venta creada).
    await waitFor(() => expect(createNotaMock).toHaveBeenCalledTimes(1));
    const payload = createNotaMock.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.id_caja).toBe('caja-1');
    expect(payload.id_sucursal).toBe('suc-1');
    expect((payload.detalles as Array<{ subtotal: number }>)[0].subtotal).toBe(3.3);

    expect((await screen.findByTestId('pos-total-cobrar')).textContent).toContain('3.83 VES');
    expect(screen.getByTestId('pos-iva-cobrar').textContent).toContain('0.53');

    // Pago 1: 2 VES en efectivo.
    fireEvent.change(screen.getByTestId('pos-pago-metodo'), { target: { value: 'met-efe' } });
    fireEvent.change(screen.getByTestId('pos-pago-moneda'), { target: { value: 'mon-ves' } });
    fireEvent.change(screen.getByTestId('pos-pago-monto'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar pago' }));
    expect(screen.getByTestId('pos-restante').textContent).toContain('1.83');

    // Pago 2: 0.05 USD a tasa 40 → 2 VES. Pagado 4 VES → vuelto 0.17.
    fireEvent.change(screen.getByTestId('pos-pago-moneda'), { target: { value: 'mon-usd' } });
    fireEvent.change(screen.getByTestId('pos-pago-monto'), { target: { value: '0.05' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar pago' }));
    expect(screen.getByTestId('pos-restante').textContent).toContain('0.00');
    expect(screen.getByTestId('pos-vuelto').textContent).toContain('0.17');

    fireEvent.click(screen.getByTestId('pos-confirmar-cobro'));
    await waitFor(() => expect(createPagoDocumentoMock).toHaveBeenCalledTimes(2));

    // Cada pago lleva su Idempotency-Key estable y distinto (PR #86/#89).
    const llamadas = createPagoDocumentoMock.mock.calls;
    const keys = llamadas.map((c) => c[3] as string);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBeTruthy();
    expect(keys[0]).not.toBe(keys[1]);
    expect(llamadas[0][0]).toBe('NOTA_VENTA');
    expect(llamadas[0][1]).toBe('nv-1');
    expect(llamadas[0][2]).toMatchObject({ monto: 2, id_moneda: 'mon-ves', tasa: 1, id_caja_fisica: 'caja-1' });
    expect(llamadas[1][2]).toMatchObject({ monto: 0.05, id_moneda: 'mon-usd', tasa: 40 });

    // Recibo 80mm con total del backend y vuelto.
    const recibo = await screen.findByTestId('pos-recibo');
    expect(screen.getByTestId('pos-recibo-total').textContent).toContain('3.83 VES');
    expect(screen.getByTestId('pos-recibo-vuelto').textContent).toContain('0.17');
    expect(within(recibo).getByText('Distribuidora Demo')).toBeInTheDocument();

    // Imprimir usa window.print (CSS 80mm; sin hardware específico aún).
    const printSpy = vi.spyOn(window, 'print').mockImplementation(() => {});
    fireEvent.click(screen.getByTestId('pos-imprimir'));
    expect(printSpy).toHaveBeenCalledTimes(1);
    printSpy.mockRestore();

    // Nueva venta limpia el carrito.
    fireEvent.click(screen.getByTestId('pos-nueva-venta'));
    expect(screen.getByTestId('pos-subtotal').textContent).toContain('0.00');
  });

  it('muestra el error del backend al crear la venta y permite reintentar', async () => {
    createNotaMock.mockRejectedValueOnce(new Error('500'));
    renderPos();
    await screen.findByText('Harina PAN');
    await agregarHarinaPorScan();

    fireEvent.click(screen.getByTestId('pos-cobrar'));
    expect((await screen.findByTestId('pos-error')).textContent).toMatch(/No se pudo registrar la venta/);

    // Reintento: ahora sí abre el cobro.
    fireEvent.click(screen.getByTestId('pos-cobrar'));
    await screen.findByTestId('pos-total-cobrar');
    expect(createNotaMock).toHaveBeenCalledTimes(2);
  });

  it('muestra el error si falla el registro de pagos (sin perder el diálogo)', async () => {
    createPagoDocumentoMock.mockRejectedValueOnce(new Error('500'));
    renderPos();
    await screen.findByText('Harina PAN');
    await agregarHarinaPorScan(3);

    fireEvent.click(screen.getByTestId('pos-cobrar'));
    await screen.findByTestId('pos-total-cobrar');
    fireEvent.change(screen.getByTestId('pos-pago-metodo'), { target: { value: 'met-efe' } });
    fireEvent.change(screen.getByTestId('pos-pago-moneda'), { target: { value: 'mon-ves' } });
    fireEvent.change(screen.getByTestId('pos-pago-monto'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar pago' }));
    fireEvent.click(screen.getByTestId('pos-confirmar-cobro'));

    expect((await screen.findByTestId('pos-cobro-error')).textContent).toMatch(/Error al registrar los pagos/);
    expect(screen.queryByTestId('pos-recibo')).not.toBeInTheDocument();
  });

  it('sin sesión de caja: al cobrar ofrece abrirla y llama abrir-sesion de la caja elegida', async () => {
    getSesionActivaMock.mockResolvedValue(null);
    renderPos();
    await screen.findByText('Harina PAN');
    expect(screen.getByTestId('pos-estado-sesion').textContent).toContain('Sin sesión de caja');

    await agregarHarinaPorScan();
    fireEvent.click(screen.getByTestId('pos-cobrar'));

    // No se crea la venta sin sesión; se ofrece abrir la caja.
    expect(createNotaMock).not.toHaveBeenCalled();
    await screen.findByText('Abrir sesión de caja');
    const lista = await screen.findByTestId('pos-cajas-lista');
    fireEvent.click(within(lista).getByText('Caja Mostrador'));
    await waitFor(() => expect(abrirSesionMock).toHaveBeenCalledWith('cf-1'));
  });

  it('valida el formulario de pago (método, moneda y monto > 0)', async () => {
    renderPos();
    await screen.findByText('Harina PAN');
    await agregarHarinaPorScan();
    fireEvent.click(screen.getByTestId('pos-cobrar'));
    await screen.findByTestId('pos-total-cobrar');

    fireEvent.click(screen.getByRole('button', { name: 'Agregar pago' }));
    expect(screen.getByText(/Selecciona método, moneda y un monto/)).toBeInTheDocument();
    // Confirmar sigue deshabilitado sin pagos que cubran el total.
    expect(screen.getByTestId('pos-confirmar-cobro')).toBeDisabled();
  });
});
