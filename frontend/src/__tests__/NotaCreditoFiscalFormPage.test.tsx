import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const navigateMock = vi.fn();
let paramsMock: Record<string, string | undefined> = {};
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock, useParams: () => paramsMock };
});

const createMock = vi.fn().mockResolvedValue({});
const updateMock = vi.fn().mockResolvedValue({});
const getByIdMock = vi.fn();
vi.mock('../services/ventas', () => ({
  notaCreditoFiscalService: {
    create: (...args: unknown[]) => createMock(...args),
    update: (...args: unknown[]) => updateMock(...args),
    getById: (...args: unknown[]) => getByIdMock(...args),
  },
}));

vi.mock('../services/clientesService', () => ({
  fetchClientes: vi.fn().mockResolvedValue([
    { id_cliente: 'c1', razon_social: 'Cliente Uno', rif: 'J-123', telefono: '555' },
    { id_cliente: 'c2', razon_social: 'Cliente Dos', rif: 'J-456', telefono: '777' },
  ]),
}));

vi.mock('../services/productosService', () => ({
  fetchProductos: vi.fn().mockResolvedValue([
    { id_producto: 'p1', nombre_producto: 'Producto Uno' },
    { id_producto: 'p2', nombre_producto: 'Producto Dos' },
  ]),
}));

import NotaCreditoFiscalFormPage from '../pages/Ventas/NotasCreditoFiscal/NotaCreditoFiscalFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NotaCreditoFiscalFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function selectCliente(user: ReturnType<typeof userEvent.setup>, optionText: RegExp) {
  // El select de cliente es el primer combobox de la cabecera.
  await user.click(screen.getAllByRole('combobox')[0]);
  await user.click(await screen.findByRole('option', { name: optionText }));
}

async function selectProductoLinea(user: ReturnType<typeof userEvent.setup>, optionText: RegExp) {
  const combos = screen.getAllByRole('combobox');
  await user.click(combos[combos.length - 1]);
  await user.click(await screen.findByRole('option', { name: optionText }));
}

/** Rellena cantidad/precio/desc de la (única) fila de detalle. */
function fillLinea(cantidad: string, precio: string, desc?: string) {
  const nums = screen.getAllByRole('spinbutton');
  fireEvent.change(nums[0], { target: { value: cantidad } });
  fireEvent.change(nums[1], { target: { value: precio } });
  if (desc !== undefined) fireEvent.change(nums[2], { target: { value: desc } });
}

describe('NotaCreditoFiscalFormPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    paramsMock = {};
    localStorage.clear();
  });

  it('renderiza en modo alta con título "Crear" y sin detalles', async () => {
    renderForm();
    expect(await screen.findByText(/crear nota de crédito fiscal/i)).toBeInTheDocument();
    expect(screen.getByText(/no hay productos agregados/i)).toBeInTheDocument();
  });

  it('bloquea el submit y exige cliente, número de control y detalles', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole('button', { name: /^crear$/i }));
    await waitFor(() => {
      expect(screen.getByText(/cliente es obligatorio/i)).toBeInTheDocument();
      expect(screen.getByText(/número de control es obligatorio/i)).toBeInTheDocument();
      expect(screen.getByText(/al menos un producto/i)).toBeInTheDocument();
    });
    expect(createMock).not.toHaveBeenCalled();
  });

  it('agrega y elimina una línea de detalle', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito fiscal/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    expect(await screen.findByRole('columnheader', { name: /% desc/i })).toBeInTheDocument();

    const deleteBtn = screen.getByTestId('DeleteIcon').closest('button')!;
    await user.click(deleteBtn);
    await waitFor(() => expect(screen.getByText(/no hay productos agregados/i)).toBeInTheDocument());
  });

  it('calcula subtotal, IVA (16%) y total de línea con decimal.js', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito fiscal/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    // 10 * 10 = 100 base; IVA 16 = 16; total 116.
    fillLinea('10', '10');
    await waitFor(() => {
      expect(screen.getByText(/Base Imponible:/)).toHaveTextContent('100,00');
      expect(screen.getByText(/^IVA:/)).toHaveTextContent('16,00');
      expect(screen.getByText(/Total:/)).toHaveTextContent('116,00');
    });
  });

  it('aplica el descuento porcentual antes del IVA', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito fiscal/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    // 10 * 10 = 100, -10% = 90 base; IVA 16% = 14,40; total 104,40.
    fillLinea('10', '10', '10');
    await waitFor(() => {
      expect(screen.getByText(/Base Imponible:/)).toHaveTextContent('90,00');
      expect(screen.getByText(/^IVA:/)).toHaveTextContent('14,40');
      expect(screen.getByText(/Total:/)).toHaveTextContent('104,40');
    });
  });

  it('envía el payload con base, IVA y total calculados con decimal.js', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito fiscal/i);

    await selectCliente(user, /cliente uno - j-123/i);
    await user.type(screen.getByLabelText(/número de control/i), 'NC-0001');
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    await selectProductoLinea(user, /producto uno/i);
    fillLinea('10', '10', '10');

    await user.click(screen.getByRole('button', { name: /^crear$/i }));
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));

    const payload = createMock.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.numero_control).toBe('NC-0001');
    expect(payload.base_imponible).toBe(90);
    expect(payload.monto_iva).toBe(14.4);
    expect(payload.monto_total).toBe(104.4);
    expect(payload.id_cliente).toMatchObject({ id_cliente: 'c1', razon_social: 'Cliente Uno' });
    expect(payload.afecta_inventario_fiscal).toBe(true);
    const detalles = payload.detalles as Array<Record<string, unknown>>;
    expect(detalles[0]).toMatchObject({
      id_producto: 'p1',
      cantidad: 10,
      precio_unitario: 10,
      descuento_porcentaje: 10,
      descuento_monto: 10,
      subtotal: 90,
      monto_impuesto: 14.4,
      total_linea: 104.4,
    });
    expect(navigateMock).toHaveBeenCalledWith('/ventas/notas-credito-fiscal');
  });

  it('valida que el descuento no supere 100', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito fiscal/i);
    await selectCliente(user, /cliente uno - j-123/i);
    await user.type(screen.getByLabelText(/número de control/i), 'NC-0002');
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    await selectProductoLinea(user, /producto uno/i);
    fillLinea('1', '10', '150');

    await user.click(screen.getByRole('button', { name: /^crear$/i }));
    await waitFor(() => {
      expect(screen.getByText(/el descuento no puede superar 100/i)).toBeInTheDocument();
    });
    expect(createMock).not.toHaveBeenCalled();
  });

  it('muestra error cuando el backend falla al guardar', async () => {
    createMock.mockRejectedValueOnce(new Error('boom'));
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito fiscal/i);
    await selectCliente(user, /cliente uno - j-123/i);
    await user.type(screen.getByLabelText(/número de control/i), 'NC-0003');
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    await selectProductoLinea(user, /producto uno/i);
    fillLinea('1', '10', '0');

    await user.click(screen.getByRole('button', { name: /^crear$/i }));
    await waitFor(() => {
      expect(screen.getByText(/error al guardar la nota de crédito fiscal/i)).toBeInTheDocument();
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('en modo edición rehidrata y llama update con el id correcto', async () => {
    paramsMock = { id: 'ncf-1' };
    getByIdMock.mockResolvedValue({
      id_cliente: { id_cliente: 'c2' },
      id_factura_origen: 'fact-9',
      numero_control: 'NC-EXIST',
      fecha_emision: '2026-02-01',
      estado: 'EMITIDA',
      motivo: 'AJUSTE_PRECIO',
      afecta_inventario_fiscal: false,
      observaciones: 'Obs fiscal',
      detalles: [
        { id_producto: 'p1', cantidad: 5, precio_unitario: 20, descuento_porcentaje: 0 },
      ],
    });
    const user = userEvent.setup();
    renderForm();

    expect(await screen.findByText(/editar nota de crédito fiscal/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByDisplayValue('NC-EXIST')).toBeInTheDocument());
    // base 100, IVA 16, total 116.
    await waitFor(() => expect(screen.getByText(/Total:/)).toHaveTextContent('116,00'));

    await user.click(screen.getByRole('button', { name: /actualizar/i }));
    await waitFor(() => expect(updateMock).toHaveBeenCalledTimes(1));
    expect(updateMock.mock.calls[0][0]).toBe('ncf-1');
    const payload = updateMock.mock.calls[0][1] as Record<string, unknown>;
    expect(payload.afecta_inventario_fiscal).toBe(false);
    expect(payload.base_imponible).toBe(100);
    expect(payload.monto_iva).toBe(16);
    expect(createMock).not.toHaveBeenCalled();
  });
});
