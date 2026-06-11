import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock, useParams: () => ({}) };
});

const postMock = vi.fn().mockResolvedValue({});
const getMock = vi.fn().mockResolvedValue({});
vi.mock('../services/api', () => ({
  get: (...args: unknown[]) => getMock(...args),
  post: (...args: unknown[]) => postMock(...args),
}));

vi.mock('../services/empresas', () => ({
  fetchEmpresas: vi.fn().mockResolvedValue([{ id_empresa: 'e1' }]),
}));

vi.mock('../services/session', () => ({
  getSessionUsuarioId: vi.fn().mockReturnValue('usr-1'),
}));

const MONEDAS = [
  {
    id: 'mea-1', nombre: 'Bolívar', activa: true, es_base: true,
    moneda: 'mon-bs', moneda_nombre: 'Bolívar', codigo_iso: 'VES', moneda_codigo_iso: 'VES',
  },
  {
    id: 'mea-2', nombre: 'Dólar', activa: true, es_base: false,
    moneda: 'mon-usd', moneda_nombre: 'Dólar', codigo_iso: 'USD', moneda_codigo_iso: 'USD',
  },
  {
    id: 'mea-3', nombre: 'Inactiva', activa: false, es_base: false,
    moneda: 'mon-x', moneda_nombre: 'Inactiva', codigo_iso: 'XXX',
  },
];

const fetchMonedasMock = vi.fn().mockResolvedValue([]);
vi.mock('../services/monedasEmpresaActiva', () => ({
  fetchMonedasEmpresaActivas: (...a: unknown[]) => fetchMonedasMock(...a),
}));

const fetchMetodosMock = vi.fn().mockResolvedValue([]);
vi.mock('../services/metodosPagoEmpresaActiva', () => ({
  fetchMetodosPagoEmpresaActivos: (...a: unknown[]) => fetchMetodosMock(...a),
}));

import TransaccionFinancieraFormPage from '../pages/Finanzas/TransaccionFinanciera/TransaccionFinancieraFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TransaccionFinancieraFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function setReferenceData() {
  fetchMonedasMock.mockResolvedValue(MONEDAS);
  fetchMetodosMock.mockResolvedValue([
    { id: 'mp-1', nombre: 'Efectivo', activa: true, metodo_pago: 'met-1' },
    { id: 'mp-2', nombre: 'Inactivo', activa: false, metodo_pago: 'met-2' },
  ]);
  getMock.mockImplementation((url: string) => {
    if (url.includes('/core/empresas/e1/')) {
      return Promise.resolve({
        id_moneda_pais: 'mon-bs',
        id_moneda_base: 'mon-bs',
        moneda_pais_nombre: 'Bolívar',
      });
    }
    if (url.includes('/finanzas/tasa-oficial-bcv/')) {
      return Promise.resolve({ valor_tasa: 40 });
    }
    return Promise.resolve({});
  });
}

async function selectMuiOption(label: RegExp, optionName: RegExp) {
  const combo = screen.getByLabelText(label);
  fireEvent.mouseDown(combo);
  const listbox = await screen.findByRole('listbox');
  fireEvent.click(within(listbox).getByText(optionName));
}

/** Llena los campos comunes requeridos por el esquema zod. */
async function fillBaseFields(monedaNombre: RegExp) {
  fireEvent.change(screen.getByLabelText(/fecha/i), { target: { value: '2026-06-11T10:30' } });
  fireEvent.change(screen.getByLabelText(/^monto \*/i), { target: { value: '100' } });
  await selectMuiOption(/moneda de transacción/i, monedaNombre);
  await selectMuiOption(/método de pago/i, /efectivo/i);
  fireEvent.change(screen.getByLabelText(/^caja/i), { target: { value: 'caja-1' } });
  await selectMuiOption(/tipo de documento asociado/i, /venta/i);
}

describe('TransaccionFinancieraFormPage (react-hook-form + zod)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigateMock.mockReset();
    fetchMonedasMock.mockResolvedValue([]);
    fetchMetodosMock.mockResolvedValue([]);
    getMock.mockResolvedValue({});
    postMock.mockResolvedValue({});
  });

  it('blocks submit and shows validation when required fields are empty', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole('button', { name: /registrar transacción/i }));
    await waitFor(() => {
      expect(screen.getByText(/la fecha es obligatoria/i)).toBeInTheDocument();
      expect(screen.getByText(/el monto es obligatorio/i)).toBeInTheDocument();
    });
    expect(postMock).not.toHaveBeenCalled();
  });

  it('con la moneda base: tasa=1, monto base = monto y el POST lleva el payload completo', async () => {
    setReferenceData();
    renderForm();

    // La moneda base detectada se muestra en el campo de solo lectura.
    await waitFor(() => expect(screen.getByLabelText(/moneda base/i)).toHaveValue('Bolívar'));
    await fillBaseFields(/bolívar/i);

    // Moneda de transacción = moneda base → tasa 1 y monto base igual al monto.
    await waitFor(() => expect(screen.getByLabelText(/tasa de cambio/i)).toHaveValue(1));
    await waitFor(() => expect(screen.getByLabelText(/monto base/i)).toHaveValue('100.00'));

    fireEvent.click(screen.getByRole('button', { name: /registrar transacción/i }));

    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1));
    const [url, payload] = postMock.mock.calls[0] as [string, Record<string, unknown>];
    expect(url).toBe('/finanzas/transacciones-financieras/');
    expect(payload).toMatchObject({
      tipo_transaccion: 'INGRESO',
      monto_transaccion: '100',
      id_moneda_transaccion: 'mon-bs',
      tasa_cambio: '1',
      monto_base: '100.00',
      id_empresa: 'e1',
      id_usuario_registro: 'usr-1',
      // Moneda de pago = moneda país → monto país igual al monto.
      monto_moneda_pais: '100.00',
    });
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/empresas/e1/transacciones-financieras'),
    );
  });

  it('con moneda distinta: consulta la tasa BCV, calcula el monto base y valida tasa menor', async () => {
    setReferenceData();
    renderForm();

    await waitFor(() => expect(screen.getByLabelText(/moneda base/i)).toHaveValue('Bolívar'));
    await fillBaseFields(/dólar/i);

    // Tasa BCV consultada para la fecha (sin la hora).
    await waitFor(() =>
      expect(getMock).toHaveBeenCalledWith(expect.stringContaining('moneda_destino=USD&fecha=2026-06-11')),
    );
    await waitFor(() => expect(screen.getByLabelText(/tasa de cambio/i)).toHaveValue(40));
    // monto base = monto / tasa = 100 / 40.
    await waitFor(() => expect(screen.getByLabelText(/monto base/i)).toHaveValue('2.50'));

    // Bajar la tasa por debajo de la oficial dispara el error de validación.
    // (La tasa visible puede ser repuesta por la re-consulta BCV del efecto,
    // pero el error solo lo limpia una edición manual válida.)
    fireEvent.change(screen.getByLabelText(/tasa de cambio/i), { target: { value: '35' } });
    expect(await screen.findByText(/no puede ser menor a la oficial bcv \(40\)/i)).toBeInTheDocument();

    // Subirla de nuevo limpia el error.
    fireEvent.change(screen.getByLabelText(/tasa de cambio/i), { target: { value: '45' } });
    await waitFor(() =>
      expect(screen.queryByText(/no puede ser menor a la oficial bcv/i)).not.toBeInTheDocument(),
    );
  });

  it('muestra el detail del backend cuando el POST falla', async () => {
    setReferenceData();
    postMock.mockRejectedValue({ detail: 'Caja sin sesión abierta' });
    renderForm();

    await waitFor(() => expect(screen.getByLabelText(/moneda base/i)).toHaveValue('Bolívar'));
    // Con la moneda NO base: la rama base del efecto limpia tasaError en cada
    // render y taparía el error de la mutación.
    await fillBaseFields(/dólar/i);
    await waitFor(() => expect(screen.getByLabelText(/tasa de cambio/i)).toHaveValue(40));
    fireEvent.click(screen.getByRole('button', { name: /registrar transacción/i }));

    expect(await screen.findByText(/caja sin sesión abierta/i)).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('solo lista monedas y métodos de pago activos', async () => {
    setReferenceData();
    renderForm();
    await waitFor(() => expect(screen.getByLabelText(/moneda base/i)).toHaveValue('Bolívar'));

    fireEvent.mouseDown(screen.getByLabelText(/moneda de transacción/i));
    const listbox = await screen.findByRole('listbox');
    expect(within(listbox).getByText('Bolívar')).toBeInTheDocument();
    expect(within(listbox).getByText('Dólar')).toBeInTheDocument();
    expect(within(listbox).queryByText('Inactiva')).not.toBeInTheDocument();
  });
});
