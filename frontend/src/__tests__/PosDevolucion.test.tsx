/**
 * Sub-fase 1.G — Devoluciones POS: flujos críticos del frontend.
 *  - buscar la venta por número y mostrar líneas con disponible por línea;
 *  - capar cantidades a lo disponible (decimal.js) y validar el formulario;
 *  - confirmar → POST con Idempotency-Key estable → recibo 80mm de devolución;
 *  - venta no encontrada y error del backend visibles;
 *  - venta fiscal: aviso de NC fiscal y recibo con base + IVA.
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
  ]),
}));

vi.mock('../services/metodosPagoEmpresaActiva', () => ({
  fetchMetodosPagoEmpresaActivos: vi.fn().mockResolvedValue([
    { id: 'met-efe', nombre_metodo: 'Efectivo', monedas: [] },
  ]),
}));

vi.mock('../services/monedasEmpresaActiva', () => ({
  fetchMonedasEmpresaActivas: vi.fn().mockResolvedValue([
    { id_moneda: 'mon-ves', nombre: 'Bolívar', codigo_iso: 'VES' },
  ]),
}));

vi.mock('../services/tasaBCV', () => ({
  fetchTasaBCV: vi.fn().mockResolvedValue({ moneda_origen: 'USD', moneda_destino: 'VES', tasa: 40, fecha: '2026-06-12' }),
}));

vi.mock('../services/clientesService', () => ({
  buscarClientes: vi.fn().mockResolvedValue([{ id_cliente: 'cli-cf', razon_social: 'Consumidor Final' }]),
  crearClienteConEmpresa: vi.fn().mockResolvedValue({ id_cliente: 'cli-nuevo' }),
}));

vi.mock('../services/pagosService', () => ({
  pagosService: { createPagoDocumento: vi.fn() },
}));

vi.mock('../services/cajasFisicasService', () => ({
  cajasFisicasService: { getCajasFisicas: vi.fn(), abrirSesion: vi.fn() },
}));

const getAlmacenesMock = vi.fn();
vi.mock('../services/almacenesService', () => ({
  almacenesService: { getAll: (...a: unknown[]) => getAlmacenesMock(...a) },
}));

const buscarVentaMock = vi.fn();
const getEstadoMock = vi.fn();
const devolverMock = vi.fn();
vi.mock('../services/devolucionesPos', () => ({
  buscarVentaPorNumero: (...a: unknown[]) => buscarVentaMock(...a),
  getEstadoDevoluciones: (...a: unknown[]) => getEstadoMock(...a),
  devolverVenta: (...a: unknown[]) => devolverMock(...a),
}));

import PosPage from '../pages/Ventas/POS/PosPage';

const ESTADO_NO_FISCAL = {
  venta: {
    id_nota_venta: 'nv-1',
    numero_nota: 'NV-0001',
    estado: 'ENTREGADA',
    fecha_nota: '2026-06-12',
    fiscal: false,
    numero_factura: null,
  },
  lineas: [
    {
      id_detalle: 'det-1',
      id_producto: 'p1',
      nombre_producto: 'Harina PAN',
      sku: 'HAR001',
      precio_unitario: '5.0000',
      cantidad_vendida: '10.0000',
      cantidad_devuelta: '4.0000',
      cantidad_disponible: '6.0000',
    },
  ],
  devoluciones: [],
};

const RESULTADO_NO_FISCAL = {
  devolucion: {
    id_devolucion: 'dev-1',
    numero_devolucion: 'DEV-0001',
    fecha_devolucion: '2026-06-12',
    estado: 'PROCESADA',
    motivo: 'CAMBIO_CLIENTE',
    monto_total: '10.0000',
  },
  nota_credito_fiscal: null,
  nota_credito_venta: { id_nota_credito: 'nc-1', numero_nota_credito: 'NCV-0001', monto_total: '10.0000' },
  pago_id: 'pago-1',
  monto_reembolsado: '10.0000',
  caja_fisica: 'Caja Mostrador',
  movimientos_inventario: 1,
  asiento_id: 'ast-1',
  asiento_iva_id: null,
};

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

async function abrirDevolucionYBuscar(numero = 'NV-0001') {
  fireEvent.click(screen.getByTestId('pos-abrir-devolucion'));
  const input = await screen.findByTestId('pos-dev-numero');
  fireEvent.change(input, { target: { value: numero } });
  fireEvent.keyDown(input, { key: 'Enter' });
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem('id_empresa', 'emp-1');
  getSesionActivaMock.mockResolvedValue(SESION);
  getAlmacenesMock.mockResolvedValue([
    { id_almacen: 'alm-1', nombre_almacen: 'Almacén Principal', id_empresa: 'emp-1' },
  ]);
  buscarVentaMock.mockResolvedValue({ id_nota_venta: 'nv-1', numero_nota: 'NV-0001', estado: 'ENTREGADA' });
  getEstadoMock.mockResolvedValue(ESTADO_NO_FISCAL);
  devolverMock.mockResolvedValue(RESULTADO_NO_FISCAL);
});

describe('PosDevolucion', () => {
  it('busca la venta por número y muestra las líneas con su disponible', async () => {
    renderPos();
    await screen.findByText('Harina PAN');
    await abrirDevolucionYBuscar();

    await screen.findByTestId('pos-dev-lineas');
    expect(buscarVentaMock).toHaveBeenCalledWith('NV-0001');
    expect(getEstadoMock).toHaveBeenCalledWith('nv-1');
    // Disponible por línea: vendida 10 − devuelta 4 = 6.
    expect(screen.getByTestId('pos-dev-disponible-det-1').textContent).toContain('6.00');
    expect(screen.getByTestId('pos-dev-tipo-venta').textContent).toMatch(/no fiscal/i);
  });

  it('venta no encontrada: aviso visible y sin llamadas extra', async () => {
    buscarVentaMock.mockResolvedValue(null);
    renderPos();
    await screen.findByText('Harina PAN');
    await abrirDevolucionYBuscar('NV-9999');

    expect((await screen.findByTestId('pos-dev-aviso')).textContent).toContain('NV-9999');
    expect(getEstadoMock).not.toHaveBeenCalled();
  });

  it('capa la cantidad a lo disponible con decimal.js antes de llamar al backend', async () => {
    renderPos();
    await screen.findByText('Harina PAN');
    await abrirDevolucionYBuscar();
    await screen.findByTestId('pos-dev-lineas');

    fireEvent.change(screen.getByTestId('pos-dev-cantidad-det-1'), { target: { value: '7' } });
    fireEvent.change(screen.getByTestId('pos-dev-metodo'), { target: { value: 'met-efe' } });
    fireEvent.click(screen.getByTestId('pos-dev-confirmar'));

    expect((await screen.findByTestId('pos-dev-error')).textContent).toContain('6.0000');
    expect(devolverMock).not.toHaveBeenCalled();
  });

  it('flujo completo: cantidades → total con decimal.js → POST con Idempotency-Key → recibo 80mm', async () => {
    renderPos();
    await screen.findByText('Harina PAN');
    await abrirDevolucionYBuscar();
    await screen.findByTestId('pos-dev-lineas');

    // 2 × 5.00 = 10.00 exacto (decimal.js, no float).
    fireEvent.change(screen.getByTestId('pos-dev-cantidad-det-1'), { target: { value: '2' } });
    expect(screen.getByTestId('pos-dev-total').textContent).toContain('10.00 VES');

    fireEvent.change(screen.getByTestId('pos-dev-metodo'), { target: { value: 'met-efe' } });
    fireEvent.change(screen.getByTestId('pos-dev-motivo'), { target: { value: 'DEFECTO' } });
    fireEvent.click(screen.getByTestId('pos-dev-confirmar'));

    await waitFor(() => expect(devolverMock).toHaveBeenCalledTimes(1));
    const [idVenta, payload, idemKey] = devolverMock.mock.calls[0] as [
      string,
      { almacen_id: string; id_metodo_pago: string; motivo: string; lineas: Array<{ id_detalle: string; cantidad: string }> },
      string,
    ];
    expect(idVenta).toBe('nv-1');
    expect(payload.almacen_id).toBe('alm-1'); // único almacén → preseleccionado
    expect(payload.id_metodo_pago).toBe('met-efe');
    expect(payload.motivo).toBe('DEFECTO');
    expect(payload.lineas).toEqual([{ id_detalle: 'det-1', cantidad: '2' }]);
    expect(idemKey).toBeTruthy(); // Idempotency-Key estable por intento

    // Recibo de devolución 80mm con el monto reembolsado del backend.
    const recibo = await screen.findByTestId('pos-dev-recibo');
    expect(screen.getByTestId('pos-dev-recibo-total').textContent).toContain('10.00 VES');
    expect(screen.getByTestId('pos-dev-recibo-nc').textContent).toContain('NCV-0001');
    expect(within(recibo).getByText('Distribuidora Demo')).toBeInTheDocument();

    // Imprimir usa window.print (mismo patrón del recibo de venta).
    const printSpy = vi.spyOn(window, 'print').mockImplementation(() => {});
    fireEvent.click(screen.getByTestId('pos-dev-imprimir'));
    expect(printSpy).toHaveBeenCalledTimes(1);
    printSpy.mockRestore();

    fireEvent.click(screen.getByTestId('pos-dev-cerrar'));
    expect(screen.queryByTestId('pos-dev-recibo')).not.toBeInTheDocument();
  });

  it('venta fiscal: aviso de NC fiscal y recibo con base, IVA y número de control', async () => {
    getEstadoMock.mockResolvedValue({
      ...ESTADO_NO_FISCAL,
      venta: { ...ESTADO_NO_FISCAL.venta, fiscal: true, numero_factura: 'FAC-0001' },
    });
    devolverMock.mockResolvedValue({
      ...RESULTADO_NO_FISCAL,
      nota_credito_venta: null,
      nota_credito_fiscal: {
        id_nota_credito_fiscal: 'ncf-1',
        numero_nota_credito: 'NC-0001',
        numero_control: '00-000123',
        base_imponible: '10.0000',
        monto_iva: '1.60',
        monto_total: '11.6000',
      },
      monto_reembolsado: '11.6000',
    });
    renderPos();
    await screen.findByText('Harina PAN');
    await abrirDevolucionYBuscar();
    await screen.findByTestId('pos-dev-lineas');
    expect(screen.getByTestId('pos-dev-tipo-venta').textContent).toContain('FAC-0001');

    fireEvent.change(screen.getByTestId('pos-dev-cantidad-det-1'), { target: { value: '2' } });
    fireEvent.change(screen.getByTestId('pos-dev-metodo'), { target: { value: 'met-efe' } });
    fireEvent.click(screen.getByTestId('pos-dev-confirmar'));

    await screen.findByTestId('pos-dev-recibo');
    expect(screen.getByTestId('pos-dev-recibo-nc').textContent).toContain('NC-0001');
    expect(screen.getByTestId('pos-dev-recibo-total').textContent).toContain('11.60 VES');
    expect(screen.getByText(/00-000123/)).toBeInTheDocument();
  });

  it('valida formulario: sin cantidades o sin método no llama al backend', async () => {
    renderPos();
    await screen.findByText('Harina PAN');
    await abrirDevolucionYBuscar();
    await screen.findByTestId('pos-dev-lineas');

    // Sin cantidades (el botón queda deshabilitado: total = 0).
    expect(screen.getByTestId('pos-dev-confirmar')).toBeDisabled();

    // Con cantidad pero sin método de reembolso.
    fireEvent.change(screen.getByTestId('pos-dev-cantidad-det-1'), { target: { value: '1' } });
    fireEvent.click(screen.getByTestId('pos-dev-confirmar'));
    expect((await screen.findByTestId('pos-dev-error')).textContent).toMatch(/método|almacén/i);
    expect(devolverMock).not.toHaveBeenCalled();
  });

  it('muestra el mensaje del backend si la devolución falla (p. ej. sobre-devolución)', async () => {
    devolverMock.mockRejectedValueOnce(
      new Error(JSON.stringify(['No se puede devolver más de lo vendido para "Harina PAN".'])),
    );
    renderPos();
    await screen.findByText('Harina PAN');
    await abrirDevolucionYBuscar();
    await screen.findByTestId('pos-dev-lineas');

    fireEvent.change(screen.getByTestId('pos-dev-cantidad-det-1'), { target: { value: '2' } });
    fireEvent.change(screen.getByTestId('pos-dev-metodo'), { target: { value: 'met-efe' } });
    fireEvent.click(screen.getByTestId('pos-dev-confirmar'));

    expect((await screen.findByTestId('pos-dev-error')).textContent).toMatch(/más de lo vendido/);
    // El diálogo sigue abierto para corregir/reintentar.
    expect(screen.getByTestId('pos-dev-confirmar')).toBeInTheDocument();
  });

  it('sin sesión de caja: el botón Devolución ofrece abrir la caja', async () => {
    getSesionActivaMock.mockResolvedValue(null);
    const { cajasFisicasService } = await import('../services/cajasFisicasService');
    (cajasFisicasService.getCajasFisicas as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [{ id_caja_fisica: 'cf-1', nombre: 'Caja Mostrador', sucursal_nombre: 'Principal' }],
      count: 1,
    });
    renderPos();
    await screen.findByText('Harina PAN');

    fireEvent.click(screen.getByTestId('pos-abrir-devolucion'));
    await screen.findByText('Abrir sesión de caja');
    expect(screen.queryByTestId('pos-dev-numero')).not.toBeInTheDocument();
  });
});
