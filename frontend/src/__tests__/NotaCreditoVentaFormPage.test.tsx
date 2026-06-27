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
  notaCreditoVentaService: {
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

import NotaCreditoVentaFormPage from '../pages/Ventas/NotasCreditoVenta/NotaCreditoVentaFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NotaCreditoVentaFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/** Selecciona la opción de cliente (select de cabecera) por texto. */
async function selectCliente(user: ReturnType<typeof userEvent.setup>, optionText: RegExp) {
  await user.click(screen.getByLabelText(/cliente/i));
  await user.click(await screen.findByRole('option', { name: optionText }));
}

/** Selecciona el producto de la primera línea de detalle. */
async function selectProductoLinea(user: ReturnType<typeof userEvent.setup>, optionText: RegExp) {
  // El select de producto dentro de la fila es un combobox sin label asociado;
  // se localiza como el último combobox renderizado.
  const combos = screen.getAllByRole('combobox');
  await user.click(combos[combos.length - 1]);
  await user.click(await screen.findByRole('option', { name: optionText }));
}

describe('NotaCreditoVentaFormPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    paramsMock = {};
    localStorage.clear();
  });

  it('renderiza en modo alta con título "Crear" y sin filas de detalle', async () => {
    renderForm();
    expect(await screen.findByText(/crear nota de crédito de venta/i)).toBeInTheDocument();
    expect(screen.getByText(/no hay productos agregados/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^crear$/i })).toBeEnabled();
  });

  it('bloquea el submit y muestra validación sin cliente ni detalles', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole('button', { name: /^crear$/i }));
    await waitFor(() => {
      expect(screen.getByText(/cliente es obligatorio/i)).toBeInTheDocument();
      expect(screen.getByText(/al menos un producto/i)).toBeInTheDocument();
    });
    expect(createMock).not.toHaveBeenCalled();
  });

  it('agrega una línea de detalle al pulsar "Agregar" y la elimina con la papelera', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito de venta/i);

    await user.click(screen.getByRole('button', { name: /agregar/i }));
    // Aparece la tabla con una fila editable.
    expect(await screen.findByRole('columnheader', { name: /producto/i })).toBeInTheDocument();
    const rows = screen.getAllByRole('row');
    // header + 1 fila de datos
    expect(rows.length).toBe(2);

    // Eliminar la fila (IconButton con DeleteIcon).
    const deleteBtn = screen.getByTestId('DeleteIcon').closest('button')!;
    await user.click(deleteBtn);
    await waitFor(() => {
      expect(screen.getByText(/no hay productos agregados/i)).toBeInTheDocument();
    });
  });

  it('recalcula el subtotal de línea y el total con decimal.js (sin floats)', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito de venta/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    // cantidad y precio que dispararían un float feo: 3 * 0.1 = 0.30000000000000004
    const numberInputs = screen.getAllByRole('spinbutton');
    const [cantidad, precio] = numberInputs;
    fireEvent.change(cantidad, { target: { value: '3' } });
    fireEvent.change(precio, { target: { value: '0.1' } });

    // El total debe ser exactamente 0,30 formateado como VES.
    await waitFor(() => {
      expect(screen.getByText(/Total:/)).toHaveTextContent('0,30');
    });
    // y nunca el artefacto de coma flotante.
    expect(screen.queryByText(/0,3000000/)).not.toBeInTheDocument();
  });

  it('envía el payload correcto (whitelist + cliente expandido + total) al crear', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito de venta/i);

    await selectCliente(user, /cliente uno - j-123/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    // Producto de la línea.
    await selectProductoLinea(user, /producto uno/i);
    const numberInputs = screen.getAllByRole('spinbutton');
    fireEvent.change(numberInputs[0], { target: { value: '2' } });
    fireEvent.change(numberInputs[1], { target: { value: '50' } });

    await user.click(screen.getByRole('button', { name: /^crear$/i }));

    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    const payload = createMock.mock.calls[0][0] as Record<string, unknown>;
    // Whitelist: NO debe filtrarse id_cliente como string plano; debe ir expandido.
    expect(payload.id_cliente).toMatchObject({ id_cliente: 'c1', razon_social: 'Cliente Uno', rif: 'J-123' });
    expect(payload.monto_total).toBe(100);
    const detalles = payload.detalles as Array<Record<string, unknown>>;
    expect(detalles).toHaveLength(1);
    expect(detalles[0]).toMatchObject({
      id_producto: 'p1',
      cantidad: 2,
      precio_unitario: 50,
      subtotal: 100,
      monto_impuesto: 0,
      total_linea: 100,
    });
    // numero/estado se mandan; campos de UI no contemplados no deben colarse.
    expect(payload.estado).toBe('BORRADOR');
    expect(navigateMock).toHaveBeenCalledWith('/ventas/notas-credito-venta');
  });

  it('valida cantidad > 0 a nivel de línea', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito de venta/i);
    await selectCliente(user, /cliente uno - j-123/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    await selectProductoLinea(user, /producto uno/i);

    const numberInputs = screen.getAllByRole('spinbutton');
    fireEvent.change(numberInputs[0], { target: { value: '0' } });
    fireEvent.change(numberInputs[1], { target: { value: '10' } });
    await user.click(screen.getByRole('button', { name: /^crear$/i }));

    await waitFor(() => {
      expect(screen.getByText(/la cantidad debe ser mayor a 0/i)).toBeInTheDocument();
    });
    expect(createMock).not.toHaveBeenCalled();
  });

  it('muestra el mensaje de error cuando el backend falla', async () => {
    createMock.mockRejectedValueOnce(new Error('boom'));
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito de venta/i);
    await selectCliente(user, /cliente uno - j-123/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    await selectProductoLinea(user, /producto uno/i);
    const numberInputs = screen.getAllByRole('spinbutton');
    fireEvent.change(numberInputs[0], { target: { value: '1' } });
    fireEvent.change(numberInputs[1], { target: { value: '10' } });
    await user.click(screen.getByRole('button', { name: /^crear$/i }));

    await waitFor(() => {
      expect(screen.getByText(/error al guardar la nota de crédito/i)).toBeInTheDocument();
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('en modo edición rehidrata los datos del servidor y llama update', async () => {
    paramsMock = { id: 'nc-1' };
    getByIdMock.mockResolvedValue({
      id_cliente: { id_cliente: 'c2' },
      fecha_emision: '2026-03-15T00:00:00Z',
      estado: 'EMITIDA',
      motivo: 'DESCUENTO',
      observaciones: 'Observación guardada',
      detalles: [
        { id_producto: 'p1', cantidad: 4, precio_unitario: 25 },
      ],
    });
    const user = userEvent.setup();
    renderForm();

    expect(await screen.findByText(/editar nota de crédito de venta/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByDisplayValue('Observación guardada')).toBeInTheDocument();
    });
    // Total rehidratado: 4 * 25 = 100.
    await waitFor(() => expect(screen.getByText(/Total:/)).toHaveTextContent('100,00'));

    await user.click(screen.getByRole('button', { name: /actualizar/i }));
    await waitFor(() => expect(updateMock).toHaveBeenCalledTimes(1));
    expect(updateMock.mock.calls[0][0]).toBe('nc-1');
    const payload = updateMock.mock.calls[0][1] as Record<string, unknown>;
    expect(payload.id_cliente).toMatchObject({ id_cliente: 'c2' });
    expect(payload.monto_total).toBe(100);
    expect(createMock).not.toHaveBeenCalled();
  });

  it('navega a la lista al pulsar Cancelar', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear nota de crédito de venta/i);
    await user.click(screen.getByRole('button', { name: /cancelar/i }));
    expect(navigateMock).toHaveBeenCalledWith('/ventas/notas-credito-venta');
  });
});
