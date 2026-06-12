/**
 * Q1/COV-2 escalón 2: tests de CajaCreatePage (creación de caja por empresa).
 * Cubre el llenado del formulario (incluye select múltiple de métodos de pago
 * y checkbox), el submit exitoso con su payload, la rama de error del backend
 * y el guard sin id_empresa.
 */
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

const createCajaMock = vi.fn();
vi.mock('../services/cajaService', () => ({
  createCaja: (...a: unknown[]) => createCajaMock(...a),
  getCajaTipoChoices: vi.fn().mockResolvedValue([
    { value: 'PRINCIPAL', display: 'Principal' },
    { value: 'REGISTRADORA', display: 'Registradora' },
  ]),
}));

vi.mock('../services/sucursales', () => ({
  fetchSucursales: vi.fn().mockResolvedValue([
    { id_sucursal: 'suc-1', nombre: 'Sucursal Centro', id_empresa: 'emp-1' },
  ]),
}));

vi.mock('../services/monedas', () => ({
  fetchMonedas: vi.fn().mockResolvedValue([
    { id_moneda: 'mon-1', nombre: 'Bolívar', codigo_iso: 'VES' },
  ]),
}));

vi.mock('../services/metodosPagoEmpresaActiva', () => ({
  fetchMetodosPagoEmpresaActivos: vi.fn().mockResolvedValue([
    { id: 'mpe-1', metodo_pago: 'mp-1', nombre: 'Efectivo' },
    { id: 'mpe-2', metodo_pago: 'mp-2', metodo_pago_nombre: 'Tarjeta' },
  ]),
}));

import CajaCreatePage from '../pages/Finanzas/Cajas/CajaCreatePage';

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CajaCreatePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  fireEvent.change(screen.getByLabelText(/nombre de caja/i), { target: { value: 'Caja Principal' } });
  // Esperar a que las opciones de los selects nativos estén cargadas.
  await screen.findByRole('option', { name: /registradora/i });
  await screen.findByRole('option', { name: /sucursal centro/i });
  await screen.findByRole('option', { name: /ves - bolívar/i });
  await screen.findByRole('option', { name: /efectivo/i });

  const selects = screen.getAllByRole('combobox');
  // Orden en el DOM: tipo_caja, sucursal, moneda.
  fireEvent.change(selects[0], { target: { value: 'REGISTRADORA' } });
  fireEvent.change(selects[1], { target: { value: 'suc-1' } });
  fireEvent.change(selects[2], { target: { value: 'mon-1' } });
  // Select múltiple de métodos de pago.
  const multi = screen.getByRole('listbox');
  await user.selectOptions(multi, ['mp-1', 'mp-2']);
}

describe('CajaCreatePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    paramsMock = { id_empresa: 'emp-1' };
    createCajaMock.mockResolvedValue({});
  });

  it('crea la caja con el payload completo y vuelve atrás al guardar', async () => {
    const user = userEvent.setup();
    renderPage();
    await fillForm(user);

    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }));

    await waitFor(() => expect(createCajaMock).toHaveBeenCalledTimes(1));
    const [empresaId, payload] = createCajaMock.mock.calls[0] as [string, Record<string, unknown>];
    expect(empresaId).toBe('emp-1');
    expect(payload).toMatchObject({
      nombre: 'Caja Principal',
      tipo_caja: 'REGISTRADORA',
      sucursal: 'suc-1',
      moneda: 'mon-1',
      activa: true,
      saldo_actual: 0,
      metodos_pago: ['mp-1', 'mp-2'],
    });
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(-1));
  });

  it('permite desmarcar "Activa" antes de crear', async () => {
    const user = userEvent.setup();
    renderPage();
    await fillForm(user);

    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }));

    await waitFor(() => expect(createCajaMock).toHaveBeenCalledTimes(1));
    const [, payload] = createCajaMock.mock.calls[0] as [string, Record<string, unknown>];
    expect(payload.activa).toBe(false);
  });

  it('muestra el error cuando el backend rechaza la creación', async () => {
    createCajaMock.mockRejectedValue(new Error('500'));
    const user = userEvent.setup();
    renderPage();
    await fillForm(user);

    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }));

    expect(await screen.findByText(/error al crear la caja/i)).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalledWith(-1);
  });

  it('no envía nada si la URL no trae id_empresa', async () => {
    paramsMock = {};
    renderPage();

    fireEvent.submit(screen.getByRole('button', { name: /^crear$/i }).closest('form') as HTMLFormElement);
    await waitFor(() => expect(createCajaMock).not.toHaveBeenCalled());
  });

  it('el botón Volver navega hacia atrás sin crear', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /volver/i }));
    expect(navigateMock).toHaveBeenCalledWith(-1);
    expect(createCajaMock).not.toHaveBeenCalled();
  });
});
