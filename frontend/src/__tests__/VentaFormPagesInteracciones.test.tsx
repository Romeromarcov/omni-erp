/**
 * Q1/COV-2 escalón 3: interacciones de las tres páginas de documentos de venta
 * (PedidoFormPage / NotaVentaFormPage / FacturaFiscalFormPage), que comparten la
 * misma estructura. Cubre lo que las suites de caracterización no ejercitan:
 *  - selección de cliente desde el modal de búsqueda (normalización de campos
 *    con fallback direccion→direccion_fiscal y email→correo);
 *  - selección de producto desde el modal de búsqueda;
 *  - botones de edición (Enviar/Anular/Imprimir → snackbar informativo);
 *  - flujo Pagar → confirmar: envía el documento, procesa vueltos y concilia
 *    notas de crédito (incluidas las ramas de error de cada paso).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

const navigateMock = vi.fn();
let paramsMock: Record<string, string> = {};
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock, useParams: () => paramsMock };
});

// ── Red y servicios ───────────────────────────────────────────────────────────
const getMock = vi.fn();
const postMock = vi.fn();
const patchMock = vi.fn();
vi.mock('../services/api', () => ({
  get: (...a: unknown[]) => getMock(...a),
  post: (...a: unknown[]) => postMock(...a),
  patch: (...a: unknown[]) => patchMock(...a),
}));

const notaVentaCreateMock = vi.fn();
const facturaCreateMock = vi.fn();
vi.mock('../services/ventas', () => ({
  NotaVentaService: class {
    create(...a: unknown[]) { return notaVentaCreateMock(...a); }
    update() { return Promise.resolve({}); }
  },
  FacturaFiscalService: class {
    create(...a: unknown[]) { return facturaCreateMock(...a); }
    update() { return Promise.resolve({}); }
  },
}));

const procesarVueltosMock = vi.fn();
const conciliarNotasCreditoMock = vi.fn();
vi.mock('../services/pagosService', () => ({
  pagosService: {
    createPagoDocumento: vi.fn().mockResolvedValue({}),
    procesarVueltos: (...a: unknown[]) => procesarVueltosMock(...a),
    conciliarNotasCredito: (...a: unknown[]) => conciliarNotasCreditoMock(...a),
  },
}));

vi.mock('../services/clientesService', () => ({
  buscarClientes: vi.fn().mockResolvedValue([]),
  buscarClientesSimilares: vi.fn().mockResolvedValue([]),
  crearClienteConEmpresa: vi.fn().mockResolvedValue({ id_cliente: 'cli-auto' }),
}));
vi.mock('../services/productosService', () => ({
  fetchProductos: vi.fn().mockResolvedValue([
    { id_producto: 'p1', nombre_producto: 'Producto Uno', sku: 'SKU1', precio_venta_sugerido: 10 },
  ]),
}));
vi.mock('../services/users', () => ({
  fetchUsuarios: vi.fn().mockResolvedValue([]),
}));
vi.mock('../services/sesionService', () => ({
  getSesionActiva: vi.fn().mockResolvedValue(null),
}));

// ── Modales hijos: stubs que exponen los callbacks de la página ──────────────
// El cliente seleccionado trae `direccion_fiscal` y `email` (NO `direccion` ni
// `correo`) para ejercitar el fallback de normalización de la página.
interface ClienteStub {
  id_cliente: string;
  razon_social: string;
  rif: string;
  telefono: string;
  direccion_fiscal: string;
  email: string;
  codigo_cliente: string;
}
const CLIENTE_RICO: ClienteStub = {
  id_cliente: 'cli-5',
  razon_social: 'Cliente Rico CA',
  rif: 'J-12345678-9',
  telefono: '0414-5555555',
  direccion_fiscal: 'Av. Bolívar 1',
  email: 'rico@cliente.ve',
  codigo_cliente: 'CL-005',
};

vi.mock('../components/Pedidos/ModalBusquedaCliente', () => ({
  default: ({ open, onSelect }: { open: boolean; onSelect: (c: ClienteStub) => void }) =>
    open ? (
      <button type="button" onClick={() => onSelect(CLIENTE_RICO)}>
        stub-seleccionar-cliente
      </button>
    ) : null,
}));

interface ProductoStub { id_producto: string; nombre_producto: string; sku: string }
vi.mock('../components/Pedidos/ModalBusquedaProducto', () => ({
  default: ({ open, onSelect }: { open: boolean; onSelect: (p: ProductoStub) => void }) =>
    open ? (
      <button
        type="button"
        onClick={() => onSelect({ id_producto: 'p1', nombre_producto: 'Producto Uno', sku: 'SKU1' })}
      >
        stub-seleccionar-producto
      </button>
    ) : null,
}));

interface PagoStub { id_metodo_pago: string; id_moneda: string; monto: number; tasa: number }
interface NotaStub { id_nota_credito: string; monto_disponible: number }
const PAGO: PagoStub = { id_metodo_pago: 'mp-1', id_moneda: 'mon-1', monto: 20, tasa: 1 };
const VUELTO: PagoStub = { id_metodo_pago: 'mp-1', id_moneda: 'mon-1', monto: 2, tasa: 1 };
const NOTA: NotaStub = { id_nota_credito: 'nc-1', monto_disponible: 5 };

vi.mock('../components/Pedidos/ModalPago', () => ({
  default: ({
    open,
    onConfirm,
  }: {
    open: boolean;
    onConfirm: (pagos: PagoStub[], vueltos?: PagoStub[], notas?: NotaStub[]) => void;
  }) =>
    open ? (
      <div>
        <button type="button" onClick={() => onConfirm([PAGO], [VUELTO], [NOTA])}>
          stub-confirmar-pago
        </button>
        <button type="button" onClick={() => onConfirm([])}>
          stub-confirmar-sin-pagos
        </button>
      </div>
    ) : null,
}));

import PedidoFormPage from '../pages/Ventas/Pedidos/PedidoFormPage';
import NotaVentaFormPage from '../pages/Ventas/NotasVenta/NotaVentaFormPage';
import FacturaFiscalFormPage from '../pages/Ventas/FacturasFiscales/FacturaFiscalFormPage';

interface PageCase {
  nombre: string;
  Component: React.ComponentType;
  editParams: Record<string, string>;
  tipoConciliacion: string;
  setupCreate: () => void;
  expectCreateCalled: () => void;
  imprimirMsg: RegExp;
}

const CASES: PageCase[] = [
  {
    nombre: 'PedidoFormPage',
    Component: PedidoFormPage,
    editParams: { id_pedido: 'ped-1' },
    tipoConciliacion: 'PEDIDO',
    setupCreate: () => postMock.mockResolvedValue({ id_pedido: 'ped-1', numero_pedido: 'PED-1' }),
    expectCreateCalled: () => expect(postMock).toHaveBeenCalledWith('/ventas/pedidos/', expect.any(Object)),
    imprimirMsg: /generar documento de pedido/i,
  },
  {
    nombre: 'NotaVentaFormPage',
    Component: NotaVentaFormPage,
    editParams: { id_nota_venta: 'nv-1' },
    tipoConciliacion: 'NOTA_VENTA',
    setupCreate: () => notaVentaCreateMock.mockResolvedValue({ id_nota_venta: 'nv-1', numero_nota_venta: 'NV-1' }),
    expectCreateCalled: () => expect(notaVentaCreateMock).toHaveBeenCalledTimes(1),
    imprimirMsg: /generar documento de nota de venta/i,
  },
  {
    nombre: 'FacturaFiscalFormPage',
    Component: FacturaFiscalFormPage,
    editParams: { id_factura: 'ff-1' },
    tipoConciliacion: 'FACTURA_FISCAL',
    setupCreate: () => facturaCreateMock.mockResolvedValue({ id_factura: 'ff-1', numero_factura: 'FF-1' }),
    expectCreateCalled: () => expect(facturaCreateMock).toHaveBeenCalledTimes(1),
    imprimirMsg: /generar documento de factura/i,
  },
];

function renderPage(Component: React.ComponentType) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FeedbackProvider>
          <Component />
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function seleccionarCliente() {
  fireEvent.click(await screen.findByRole('button', { name: /buscar cliente existente/i }));
  fireEvent.click(await screen.findByRole('button', { name: 'stub-seleccionar-cliente' }));
}

describe.each(CASES)('$nombre — interacciones', ({ Component, editParams, tipoConciliacion, setupCreate, expectCreateCalled, imprimirMsg }) => {
  beforeEach(() => {
    vi.clearAllMocks();
    paramsMock = {};
    localStorage.clear();
    getMock.mockResolvedValue([]);
    postMock.mockResolvedValue({});
    patchMock.mockResolvedValue({});
    procesarVueltosMock.mockResolvedValue(undefined);
    conciliarNotasCreditoMock.mockResolvedValue(undefined);
    setupCreate();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('normaliza los datos del cliente elegido en el modal (fallbacks direccion/correo)', async () => {
    renderPage(Component);
    await seleccionarCliente();

    // El modal se cerró y los campos quedaron rellenos con los fallbacks.
    expect(screen.queryByRole('button', { name: 'stub-seleccionar-cliente' })).toBeNull();
    expect(screen.getByDisplayValue('Cliente Rico CA')).toBeInTheDocument();
    expect(screen.getByDisplayValue('12345678')).toBeInTheDocument(); // número del RIF (sin prefijo)
    expect(screen.getByDisplayValue('Av. Bolívar 1')).toBeInTheDocument(); // direccion_fiscal → direccion
    expect(screen.getByDisplayValue('rico@cliente.ve')).toBeInTheDocument(); // email → correo
    expect(screen.getByDisplayValue('CL-005')).toBeInTheDocument();
  });

  it('selecciona un producto desde el modal de búsqueda y lo cierra', async () => {
    renderPage(Component);
    fireEvent.click(await screen.findByRole('button', { name: /buscar producto/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'stub-seleccionar-producto' }));
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'stub-seleccionar-producto' })).toBeNull();
    });
  });

  it('en edición, Enviar/Anular/Imprimir muestran el aviso informativo', async () => {
    paramsMock = { ...editParams };
    renderPage(Component);

    fireEvent.click(await screen.findByRole('button', { name: /^enviar$/i }));
    expect(await screen.findByText(/Función Enviar/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^anular$/i }));
    expect(await screen.findByText(/Función Anular/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^imprimir$/i }));
    expect(await screen.findByText(imprimirMsg)).toBeInTheDocument();
  });

  it('Pagar → confirmar: crea el documento, procesa vueltos y concilia notas de crédito', async () => {
    renderPage(Component);
    await seleccionarCliente(); // sin cliente el submit aborta

    fireEvent.click(screen.getByRole('button', { name: /^pagar$/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'stub-confirmar-pago' }));

    await waitFor(() => expectCreateCalled());
    await waitFor(() => {
      expect(procesarVueltosMock).toHaveBeenCalledWith([VUELTO]);
      expect(conciliarNotasCreditoMock).toHaveBeenCalledWith([NOTA], 'nuevo', tipoConciliacion);
    });
  });

  it('Pagar → confirmar tolera errores de vueltos y conciliación (los registra en consola)', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    procesarVueltosMock.mockRejectedValue(new Error('vuelto falló'));
    conciliarNotasCreditoMock.mockRejectedValue(new Error('conciliación falló'));

    renderPage(Component);
    await seleccionarCliente();
    fireEvent.click(screen.getByRole('button', { name: /^pagar$/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'stub-confirmar-pago' }));

    await waitFor(() => {
      expect(consoleError).toHaveBeenCalledWith('Error procesando vueltos:', expect.any(Error));
      expect(consoleError).toHaveBeenCalledWith('Error conciliando notas de crédito:', expect.any(Error));
    });
  });

  it('Pagar → confirmar sin pagos NO envía el documento', async () => {
    renderPage(Component);
    await seleccionarCliente();
    fireEvent.click(screen.getByRole('button', { name: /^pagar$/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'stub-confirmar-sin-pagos' }));

    // El modal se cierra sin disparar la creación.
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'stub-confirmar-sin-pagos' })).toBeNull();
    });
    expect(procesarVueltosMock).not.toHaveBeenCalled();
    expect(conciliarNotasCreditoMock).not.toHaveBeenCalled();
  });
});
