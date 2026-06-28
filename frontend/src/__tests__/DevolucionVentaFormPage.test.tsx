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
  devolucionVentaService: {
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

import DevolucionVentaFormPage from '../pages/Ventas/DevolucionesVenta/DevolucionVentaFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DevolucionVentaFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function selectCliente(user: ReturnType<typeof userEvent.setup>, optionText: RegExp) {
  // El cliente es el primer combobox de la cabecera.
  await user.click(screen.getAllByRole('combobox')[0]);
  await user.click(await screen.findByRole('option', { name: optionText }));
}

async function selectProductoLinea(user: ReturnType<typeof userEvent.setup>, optionText: RegExp) {
  // El select de producto es el primer combobox de la fila de detalle (3 en cabecera).
  const combos = screen.getAllByRole('combobox');
  // cabecera: cliente, motivo, estado (3). Producto de la fila = índice 3.
  await user.click(combos[3]);
  await user.click(await screen.findByRole('option', { name: optionText }));
}

function fillLinea(cantidad: string, precio: string) {
  const nums = screen.getAllByRole('spinbutton');
  fireEvent.change(nums[0], { target: { value: cantidad } });
  fireEvent.change(nums[1], { target: { value: precio } });
}

describe('DevolucionVentaFormPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    paramsMock = {};
    localStorage.clear();
  });

  it('renderiza en modo alta con título "Crear" y sin detalles', async () => {
    renderForm();
    expect(await screen.findByText(/crear devolución de venta/i)).toBeInTheDocument();
    expect(screen.getByText(/no hay productos agregados/i)).toBeInTheDocument();
    // El checkbox de generar NC viene marcado por defecto.
    expect(screen.getByRole('checkbox')).toBeChecked();
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

  it('agrega y elimina una línea de detalle', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear devolución de venta/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    expect(await screen.findByRole('columnheader', { name: /acción inventario/i })).toBeInTheDocument();

    const deleteBtn = screen.getByTestId('DeleteIcon').closest('button')!;
    await user.click(deleteBtn);
    await waitFor(() => expect(screen.getByText(/no hay productos agregados/i)).toBeInTheDocument());
  });

  it('calcula el subtotal/total de la devolución con decimal.js (sin floats)', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear devolución de venta/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    // 3 * 0.1 = 0,30 exacto.
    fillLinea('3', '0.1');
    await waitFor(() => {
      expect(screen.getByText(/Total de la Devolución:/)).toHaveTextContent('0,30');
    });
    expect(screen.queryByText(/0,3000000/)).not.toBeInTheDocument();
  });

  it('muestra el aviso de NC fiscal cuando "generar nota de crédito" está activo', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear devolución de venta/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    fillLinea('1', '100');
    await waitFor(() =>
      expect(screen.getByText(/se generará automáticamente una nota de crédito fiscal/i)).toBeInTheDocument(),
    );

    // Al desmarcar, el aviso desaparece.
    await user.click(screen.getByRole('checkbox'));
    await waitFor(() =>
      expect(screen.queryByText(/se generará automáticamente una nota de crédito fiscal/i)).not.toBeInTheDocument(),
    );
  });

  it('envía el payload con whitelist + generar_nota_credito + total decimal', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear devolución de venta/i);

    await selectCliente(user, /cliente uno - j-123/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    await selectProductoLinea(user, /producto uno/i);
    fillLinea('2', '50');

    await user.click(screen.getByRole('button', { name: /^crear$/i }));
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));

    const payload = createMock.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.monto_total).toBe(100);
    expect(payload.generar_nota_credito).toBe(true);
    expect(payload.id_cliente).toMatchObject({ id_cliente: 'c1', razon_social: 'Cliente Uno' });
    const detalles = payload.detalles as Array<Record<string, unknown>>;
    expect(detalles[0]).toMatchObject({
      id_producto: 'p1',
      cantidad_devuelta: 2,
      precio_unitario: 50,
      subtotal: 100,
      estado_producto: 'BUENO',
      accion_inventario: 'REINTEGRAR',
    });
    expect(navigateMock).toHaveBeenCalledWith('/ventas/devoluciones-venta');
  });

  it('valida cantidad_devuelta > 0', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear devolución de venta/i);
    await selectCliente(user, /cliente uno - j-123/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    await selectProductoLinea(user, /producto uno/i);
    fillLinea('0', '10');

    await user.click(screen.getByRole('button', { name: /^crear$/i }));
    await waitFor(() => {
      expect(screen.getByText(/la cantidad debe ser mayor a 0/i)).toBeInTheDocument();
    });
    expect(createMock).not.toHaveBeenCalled();
  });

  it('muestra error cuando el backend falla', async () => {
    createMock.mockRejectedValueOnce(new Error('boom'));
    const user = userEvent.setup();
    renderForm();
    await screen.findByText(/crear devolución de venta/i);
    await selectCliente(user, /cliente uno - j-123/i);
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    await selectProductoLinea(user, /producto uno/i);
    fillLinea('1', '10');

    await user.click(screen.getByRole('button', { name: /^crear$/i }));
    await waitFor(() => {
      expect(screen.getByText(/error al guardar la devolución/i)).toBeInTheDocument();
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('en modo edición rehidrata y llama update; generar_nota_credito deriva de id_nota_credito_generada', async () => {
    paramsMock = { id: 'dev-1' };
    getByIdMock.mockResolvedValue({
      id_cliente: { id_cliente: 'c2' },
      id_factura_origen: 'fact-2',
      fecha_devolucion: '2026-04-10',
      estado: 'APROBADA',
      motivo_devolucion: 'GARANTIA',
      id_nota_credito_generada: null,
      observaciones: 'Devolución previa',
      detalles: [
        {
          id_producto: 'p1',
          cantidad_devuelta: 3,
          precio_unitario: 30,
          estado_producto: 'DEFECTUOSO',
          accion_inventario: 'CUARENTENA',
          observaciones: 'roto',
        },
      ],
    });
    const user = userEvent.setup();
    renderForm();

    expect(await screen.findByText(/editar devolución de venta/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByDisplayValue('Devolución previa')).toBeInTheDocument());
    // total 3 * 30 = 90.
    await waitFor(() => expect(screen.getByText(/Total de la Devolución:/)).toHaveTextContent('90,00'));
    // sin id_nota_credito_generada -> checkbox desmarcado.
    expect(screen.getByRole('checkbox')).not.toBeChecked();

    await user.click(screen.getByRole('button', { name: /actualizar/i }));
    await waitFor(() => expect(updateMock).toHaveBeenCalledTimes(1));
    expect(updateMock.mock.calls[0][0]).toBe('dev-1');
    const payload = updateMock.mock.calls[0][1] as Record<string, unknown>;
    expect(payload.monto_total).toBe(90);
    expect(payload.generar_nota_credito).toBe(false);
    expect(createMock).not.toHaveBeenCalled();
  });
});
