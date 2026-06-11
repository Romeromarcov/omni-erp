import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
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
const getCajaMock = vi.fn().mockResolvedValue(null);
vi.mock('../services/cajasFisicasService', () => ({
  cajasFisicasService: {
    createCajaFisica: (...args: unknown[]) => createMock(...args),
    updateCajaFisica: (...args: unknown[]) => updateMock(...args),
    getCajaFisica: (...args: unknown[]) => getCajaMock(...args),
    getTipoCajaChoices: vi.fn().mockResolvedValue([{ value: 'REGISTRADORA', display: 'Registradora' }]),
  },
}));

vi.mock('../services/monedasEmpresaActiva', () => ({
  fetchMonedasEmpresaActivas: vi.fn().mockResolvedValue([
    { id_moneda: 'm1', nombre: 'Bolívar', codigo_iso: 'VES' },
  ]),
}));

import CajaFisicaFormPage from '../pages/Finanzas/Cajas/CajaFisicaFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CajaFisicaFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function selectMoneda() {
  fireEvent.mouseDown(screen.getByLabelText(/moneda/i));
  const listbox = await screen.findByRole('listbox');
  fireEvent.click(await within(listbox).findByText(/bolívar/i));
}

describe('CajaFisicaFormPage (react-hook-form + zod)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    paramsMock = {};
    localStorage.setItem('id_empresa', 'e1');
    createMock.mockResolvedValue({});
    updateMock.mockResolvedValue({});
  });

  it('blocks submit and shows validation when nombre and moneda are empty', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole('button', { name: /crear/i }));
    await waitFor(() => {
      expect(screen.getByText(/el nombre es obligatorio/i)).toBeInTheDocument();
      expect(screen.getByText(/debe seleccionar una moneda/i)).toBeInTheDocument();
    });
    expect(createMock).not.toHaveBeenCalled();
  });

  it('crea la caja física con empresa y saldos iniciales y navega tras el éxito', async () => {
    renderForm();

    fireEvent.change(screen.getByLabelText(/^nombre \*/i), { target: { value: 'Caja Física 1' } });
    await selectMoneda();
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }));

    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    const [payload] = createMock.mock.calls[0] as [Record<string, unknown>];
    expect(payload).toMatchObject({
      nombre: 'Caja Física 1',
      moneda: 'm1',
      empresa: 'e1',
      saldo_inicial: 0,
      saldo_actual: 0,
      esta_abierta: false,
    });
    expect(await screen.findByText(/caja física creada correctamente/i)).toBeInTheDocument();
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/finanzas/cajas-fisicas'), { timeout: 3000 });
  });

  it('muestra el error del backend al fallar la creación', async () => {
    createMock.mockRejectedValue(new Error('500'));
    renderForm();

    fireEvent.change(screen.getByLabelText(/^nombre \*/i), { target: { value: 'Caja Falla' } });
    await selectMoneda();
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }));

    expect(await screen.findByText(/error al crear la caja física/i)).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('en edición carga la caja existente y llama update al guardar', async () => {
    paramsMock = { id: 'cf-9', action: 'editar' };
    getCajaMock.mockResolvedValue({
      id: 'cf-9',
      nombre: 'Caja Editada',
      tipo_caja: 'REGISTRADORA',
      descripcion: 'desc',
      sucursal: '',
      moneda: 'm1',
      nombre_dispositivo: '',
      tipo_dispositivo: 'PC',
      identificador_dispositivo: '',
      descripcion_dispositivo: '',
      requiere_sesion_activa: true,
      activa: true,
    });
    renderForm();

    expect(await screen.findByText(/editar caja física/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByDisplayValue('Caja Editada')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /actualizar/i }));

    await waitFor(() => expect(updateMock).toHaveBeenCalledTimes(1));
    const [id, payload] = updateMock.mock.calls[0] as [string, Record<string, unknown>];
    expect(id).toBe('cf-9');
    expect(payload).toMatchObject({ nombre: 'Caja Editada', moneda: 'm1' });
    expect(createMock).not.toHaveBeenCalled();
    expect(await screen.findByText(/caja física actualizada correctamente/i)).toBeInTheDocument();
  });
});
