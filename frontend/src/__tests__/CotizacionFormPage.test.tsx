/**
 * FE-CRIT-1 characterization tests for CotizacionFormPage.
 * Captures CURRENT behavior before/after the react-hook-form migration:
 *  (a) empty/invalid submit does NOT call the create mutation;
 *  (b) editing an existing record loads its values into the form;
 *  (c) a valid (edit-loaded) submit calls the update mutation exactly once
 *      with the expected payload shape.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

const navigateMock = vi.fn();
let paramsMock: Record<string, string> = {};
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock, useParams: () => paramsMock };
});

// ── Network layer (services/api) ─────────────────────────────────────────────
const postMock = vi.fn().mockResolvedValue({ id_cotizacion: 'cot-new', numero_cotizacion: 'COT-1' });
const patchMock = vi.fn().mockResolvedValue({ id_cotizacion: 'cot-1', numero_cotizacion: 'COT-1' });
const getMock = vi.fn();
vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return {
    ...actual,
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    patch: (...a: unknown[]) => patchMock(...a),
  };
});

// Cotizacion submit goes through cotizacionService.create/update.
vi.mock('../services/ventas', () => ({
  cotizacionService: {
    create: (...a: unknown[]) => postMock(...a),
    update: (...a: unknown[]) => patchMock(...a),
  },
}));

// ── Side-effect services invoked by useDocumentoVentaBase ────────────────────
vi.mock('../services/productosService', () => ({
  fetchProductos: vi.fn().mockResolvedValue([
    { id_producto: 'p1', nombre_producto: 'Producto Uno', sku: 'SKU1', precio_venta_sugerido: 10 },
  ]),
}));
vi.mock('../services/clientesService', () => ({
  buscarClientes: vi.fn().mockResolvedValue([
    {
      id_cliente: 'cli-buscado',
      razon_social: 'Cliente Buscado',
      rif: 'J-999',
      telefono: '0414',
      direccion_fiscal: 'Av. Siempreviva',
      email: 'cli@example.com',
      codigo_cliente: 'COD-1',
    },
  ]),
  buscarClientesSimilares: vi.fn().mockResolvedValue([]),
  crearClienteConEmpresa: vi.fn().mockResolvedValue({ id_cliente: 'c-auto' }),
}));
vi.mock('../services/users', () => ({
  fetchUsuarios: vi.fn().mockResolvedValue([]),
}));
vi.mock('../services/sesionService', () => ({
  getSesionActiva: vi.fn().mockResolvedValue(null),
}));
vi.mock('../services/pagosService', () => ({
  pagosService: {
    createPagoDocumento: vi.fn().mockResolvedValue({}),
    procesarVueltos: vi.fn().mockResolvedValue(undefined),
    conciliarNotasCredito: vi.fn().mockResolvedValue(undefined),
  },
}));

import CotizacionFormPage from '../pages/Ventas/Cotizaciones/CotizacionFormPage';

const EXISTING_COTIZACION = {
  id_cotizacion: 'cot-1',
  numero_cotizacion: 'COT-0001',
  fecha_cotizacion: '2026-01-10',
  fecha_vencimiento: '2026-02-10',
  estado: 'BORRADOR',
  id_empresa: 'emp-1',
  id_cliente: { id_cliente: 'cli-1' },
  id_moneda: 'mon-1',
  observaciones: 'Observacion existente',
  condiciones_comerciales: 'Pago a 30 dias',
  detalles: [
    { id_producto: 'p1', cantidad: 2, precio_unitario: 10, descuento_porcentaje: 0, sku: 'SKU1', producto: 'Producto Uno' },
  ],
};

function setGetRouting(editRecord?: unknown) {
  getMock.mockImplementation((url: string) => {
    if (editRecord && url.includes('/ventas/cotizaciones/')) return Promise.resolve(editRecord);
    return Promise.resolve([]); // cajas-usuario, sucursales, empresas, etc.
  });
}

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FeedbackProvider>
          <CotizacionFormPage />
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CotizacionFormPage (characterization)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    paramsMock = {};
    localStorage.clear();
    setGetRouting();
  });

  it('does not call the create mutation on an empty/invalid submit', async () => {
    renderForm();
    const submit = await screen.findByRole('button', { name: /guardar cotización/i });
    // Sin cliente seleccionado el guardado está bloqueado.
    expect(submit).toBeDisabled();
    expect(postMock).not.toHaveBeenCalled();
  });

  it('loads values when editing an existing cotización', async () => {
    paramsMock = { id: 'cot-1' };
    setGetRouting(EXISTING_COTIZACION);
    renderForm();
    await waitFor(() => {
      expect(screen.getByDisplayValue('Observacion existente')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Pago a 30 dias')).toBeInTheDocument();
    });
  });

  it('calls the update mutation exactly once with detalles on a valid edit submit', async () => {
    paramsMock = { id: 'cot-1' };
    localStorage.setItem('id_sucursal', 'suc-1');
    setGetRouting(EXISTING_COTIZACION);
    renderForm();

    const submit = await screen.findByRole('button', { name: /guardar cotización/i });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.submit(submit.closest('form')!);
    await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1));
    expect(postMock).not.toHaveBeenCalled();
    const [, payload] = patchMock.mock.calls[0] as [string, Record<string, unknown>];
    expect(Array.isArray(payload.detalles)).toBe(true);
    expect((payload.detalles as unknown[]).length).toBe(1);
  });

  it('renderiza en modo alta con el título "Nueva Cotización" y submit deshabilitado', async () => {
    renderForm();
    expect(await screen.findByText(/nueva cotización/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /guardar cotización/i })).toBeDisabled();
    // Sin líneas, no hay preview.
    expect(screen.queryByText(/preview de la cotización/i)).not.toBeInTheDocument();
  });

  it('selecciona un cliente desde el modal de búsqueda (cubre getFieldString)', async () => {
    localStorage.setItem('id_empresa', 'emp-1');
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/nueva cotización/i);

    await user.click(screen.getByRole('button', { name: /buscar cliente existente/i }));
    // El modal busca al teclear; el mock devuelve un cliente.
    const dialog = await screen.findByRole('dialog');
    const input = within(dialog).getByPlaceholderText(/buscar por nombre/i);
    await user.type(input, 'Cliente');
    const seleccionar = await within(dialog).findAllByRole('button', { name: /seleccionar/i });
    await user.click(seleccionar[seleccionar.length - 1]);

    // Los datos del cliente se vuelcan en el formulario de cliente.
    await waitFor(() => {
      expect(screen.getByDisplayValue('Cliente Buscado')).toBeInTheDocument();
      // direccion derivada de direccion_fiscal y correo de email (getFieldString).
      expect(screen.getByDisplayValue('Av. Siempreviva')).toBeInTheDocument();
      expect(screen.getByDisplayValue('cli@example.com')).toBeInTheDocument();
    });
    // El número de RIF se separa del prefijo (J | 999).
    expect(screen.getByDisplayValue('999')).toBeInTheDocument();
    // Al haber cliente, el submit se habilita.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /guardar cotización/i })).toBeEnabled(),
    );
  });

  it('agrega una línea desde el modal de producto y calcula el total con decimal.js', async () => {
    localStorage.setItem('id_empresa', 'emp-1');
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/nueva cotización/i);

    // Abrir modal de producto y seleccionar (esperando a que carguen los productos).
    await user.click(screen.getByRole('button', { name: /buscar producto/i }));
    const dialog = await screen.findByRole('dialog');
    const buscar = within(dialog).getByPlaceholderText(/buscar por nombre/i);
    await user.type(buscar, 'Producto');
    await user.click(await within(dialog).findByRole('button', { name: /^Seleccionar$/ }));

    // Esperar a que el modal se cierre por completo (deja de bloquear el foco/aria).
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    // El precio se autocompleta (10); fijar cantidad = 3.
    const cantidad = await screen.findByLabelText(/^cantidad$/i);
    fireEvent.change(cantidad, { target: { value: '3' } });
    // Agregar la línea.
    await user.click(screen.getByRole('button', { name: /^agregar$/i }));

    // Aparece la preview con la línea y el total 3 * 10 = 30.00.
    expect(await screen.findByText(/preview de la cotización/i)).toBeInTheDocument();
    // El total/subtotal calculado con decimal.js aparece como 30.00 (no 30.00000001).
    expect(screen.getAllByText('30.00').length).toBeGreaterThan(0);

    // Eliminar la línea.
    await user.click(screen.getByRole('button', { name: /eliminar/i }));
    await waitFor(() =>
      expect(screen.queryByText(/preview de la cotización/i)).not.toBeInTheDocument(),
    );
  });

  it('abre el modal de Pago con el monto sumado de los detalles', async () => {
    localStorage.setItem('id_empresa', 'emp-1');
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/nueva cotización/i);

    // Agregar una línea (producto precio 10 x cantidad 2 = 20).
    await user.click(screen.getByRole('button', { name: /buscar producto/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByPlaceholderText(/buscar por nombre/i), 'Producto');
    await user.click(await within(dialog).findByRole('button', { name: /^Seleccionar$/ }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const cantidad = await screen.findByLabelText(/^cantidad$/i);
    fireEvent.change(cantidad, { target: { value: '2' } });
    await user.click(screen.getByRole('button', { name: /^agregar$/i }));
    await screen.findByText(/preview de la cotización/i);

    // Pulsar Pagar abre el ModalPago.
    await user.click(screen.getByRole('button', { name: /^pagar$/i }));
    // ModalPago se abre (cabecera "Registrar Pago").
    expect(await screen.findByText(/registrar pago/i)).toBeInTheDocument();
  });

  it('los botones Enviar/Anular/Imprimir disparan un aviso informativo en edición', async () => {
    paramsMock = { id: 'cot-1' };
    localStorage.setItem('id_sucursal', 'suc-1');
    setGetRouting(EXISTING_COTIZACION);
    const user = userEvent.setup();
    renderForm();

    const enviar = await screen.findByRole('button', { name: /^enviar$/i });
    await user.click(enviar);
    expect(await screen.findByText(/convertir en nota de venta/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^anular$/i }));
    expect(await screen.findByText(/cambiar estado a anulado/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^imprimir$/i }));
    expect(await screen.findByText(/generar documento de cotización/i)).toBeInTheDocument();
  });

  it('navega a la lista al pulsar Cancelar', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/nueva cotización/i);
    await user.click(screen.getByRole('button', { name: /cancelar/i }));
    expect(navigateMock).toHaveBeenCalledWith('/ventas/cotizaciones');
  });
});
