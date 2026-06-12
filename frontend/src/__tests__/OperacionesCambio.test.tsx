import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/tesoreriaService', () => ({
  tesoreriaService: {
    getOperacionesCambioPaginated: vi.fn(),
    crearOperacionCambio: vi.fn(),
  },
}));

vi.mock('../services/monedasEmpresaActiva', () => ({
  fetchMonedasEmpresaActivas: vi.fn(),
}));

vi.mock('../services/metodosPagoEmpresaActiva', () => ({
  fetchMetodosPagoEmpresaActivos: vi.fn(),
}));

import { tesoreriaService } from '../services/tesoreriaService';
import { fetchMonedasEmpresaActivas } from '../services/monedasEmpresaActiva';
import { fetchMetodosPagoEmpresaActivos } from '../services/metodosPagoEmpresaActiva';
import OperacionesCambioListPage from '../pages/Tesoreria/OperacionesCambioListPage';
import OperacionCambioFormPage from '../pages/Tesoreria/OperacionCambioFormPage';

const operacion = {
  id: 1,
  empresa: 'emp-1',
  numero_operacion: 'CD-001',
  fecha_operacion: '2026-06-10T00:00:00Z',
  tipo_operacion: 'COMPRA',
  moneda_origen: 'mon-usd',
  moneda_destino: 'mon-ves',
  monto_origen: '100.1000',
  tasa_cambio: '36.123456',
  monto_destino: '3615.9579',
  comision: '0.0000',
  caja_origen: null,
  caja_destino: null,
  banco_origen: null,
  banco_destino: null,
  metodo_pago_origen: 'mp-1',
  metodo_pago_destino: 'mp-2',
  referencia_transaccion_origen: null,
  referencia_transaccion_destino: null,
  observaciones: null,
  activo: true,
  fecha_creacion: '2026-06-10T10:00:00Z',
};

const monedas = [
  { id_moneda: 'mon-usd', nombre: 'Dólar', codigo_iso: 'USD' },
  { id_moneda: 'mon-ves', nombre: 'Bolívar', codigo_iso: 'VES' },
];

const metodos = [
  { id: 'mp-1', nombre_metodo: 'Efectivo', monedas: [] },
  { id: 'mp-2', nombre_metodo: 'Transferencia', monedas: [] },
];

function renderList() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/tesoreria/cambio-divisa']}>
          <Routes>
            <Route path="/tesoreria/cambio-divisa" element={<OperacionesCambioListPage />} />
            <Route path="/tesoreria/cambio-divisa/nueva" element={<div>FORM-CAMBIO</div>} />
          </Routes>
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/tesoreria/cambio-divisa/nueva']}>
          <Routes>
            <Route path="/tesoreria/cambio-divisa/nueva" element={<OperacionCambioFormPage />} />
            <Route path="/tesoreria/cambio-divisa" element={<div>LISTA-CAMBIO</div>} />
            <Route path="/contabilidad/mapeos" element={<div>PANTALLA-MAPEOS</div>} />
          </Routes>
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

async function llenarFormulario(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/Número/), 'CD-002');
  await user.click(screen.getByLabelText(/Moneda origen/));
  await user.click(await screen.findByRole('option', { name: /USD — Dólar/ }));
  await user.click(screen.getByLabelText(/Moneda destino/));
  await user.click(await screen.findByRole('option', { name: /VES — Bolívar/ }));
  await user.type(screen.getByLabelText(/Monto origen/), '100.10');
  await user.type(screen.getByLabelText(/^Tasa/), '36.123456');
  await user.click(screen.getByLabelText(/Método de pago \(egreso\)/));
  await user.click(await screen.findByRole('option', { name: 'Efectivo' }));
  await user.click(screen.getByLabelText(/Método de pago \(ingreso\)/));
  await user.click(await screen.findByRole('option', { name: 'Transferencia' }));
}

describe('OperacionesCambioListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tesoreriaService.getOperacionesCambioPaginated).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [operacion],
    });
  });

  afterEach(() => cleanup());

  it('lista las operaciones con montos y tasa en precisión completa', async () => {
    renderList();
    expect(await screen.findByText('CD-001')).toBeInTheDocument();
    expect(screen.getByText('100.1000')).toBeInTheDocument();
    expect(screen.getByText('36.123456')).toBeInTheDocument();
    expect(screen.getByText('3615.9579')).toBeInTheDocument();
  });

  it('navega al formulario de nueva operación', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('CD-001');
    await user.click(screen.getByRole('button', { name: 'Nueva operación' }));
    expect(await screen.findByText('FORM-CAMBIO')).toBeInTheDocument();
  });
});

describe('OperacionCambioFormPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    vi.mocked(fetchMonedasEmpresaActivas).mockResolvedValue(monedas);
    vi.mocked(fetchMetodosPagoEmpresaActivos).mockResolvedValue(metodos);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('calcula monto destino = monto × tasa con decimal.js (sin float)', { timeout: 15000 }, async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByLabelText(/Número/);

    await user.type(screen.getByLabelText(/Monto origen/), '100.10');
    await user.type(screen.getByLabelText(/^Tasa/), '36.123456');
    // 100.10 × 36.123456 = 3615.9579 (4 decimales exactos con Decimal).
    expect(screen.getByText(/3615\.9579/)).toBeInTheDocument();
  });

  it('envía el payload con montos string y monto_destino calculado', async () => {
    vi.mocked(tesoreriaService.crearOperacionCambio).mockResolvedValue(operacion);
    const user = userEvent.setup();
    renderForm();
    await screen.findByLabelText(/Número/);
    await llenarFormulario(user);

    await user.click(screen.getByRole('button', { name: 'Registrar operación' }));

    await waitFor(() => {
      expect(tesoreriaService.crearOperacionCambio).toHaveBeenCalledWith(
        expect.objectContaining({
          empresa: 'emp-1',
          numero_operacion: 'CD-002',
          tipo_operacion: 'COMPRA',
          moneda_origen: 'mon-usd',
          moneda_destino: 'mon-ves',
          monto_origen: '100.10',
          tasa_cambio: '36.123456',
          monto_destino: '3615.9579',
          comision: '0',
          metodo_pago_origen: 'mp-1',
          metodo_pago_destino: 'mp-2',
        }),
      );
    });
    expect(await screen.findByText('LISTA-CAMBIO')).toBeInTheDocument();
  });

  it('ante el 422 sin mapeo CAMBIO_DIVISA muestra el error con link a Mapeos Contables', async () => {
    vi.mocked(tesoreriaService.crearOperacionCambio).mockRejectedValue(
      new Error(
        JSON.stringify({
          error: 'No hay mapeo contable para CAMBIO_DIVISA. Configúrelo antes de operar.',
        }),
      ),
    );
    const user = userEvent.setup();
    renderForm();
    await screen.findByLabelText(/Número/);
    await llenarFormulario(user);

    await user.click(screen.getByRole('button', { name: 'Registrar operación' }));

    expect(await screen.findByText(/No hay mapeo contable para CAMBIO_DIVISA/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /Mapeos Contables/ });
    await user.click(link);
    expect(await screen.findByText('PANTALLA-MAPEOS')).toBeInTheDocument();
  });

  it('rechaza moneda destino igual a la de origen sin llamar al servicio', async () => {
    const user = userEvent.setup();
    renderForm();
    await screen.findByLabelText(/Número/);

    await user.type(screen.getByLabelText(/Número/), 'CD-003');
    await user.click(screen.getByLabelText(/Moneda origen/));
    await user.click(await screen.findByRole('option', { name: /USD — Dólar/ }));
    await user.click(screen.getByLabelText(/Moneda destino/));
    await user.click(await screen.findByRole('option', { name: /USD — Dólar/ }));
    await user.type(screen.getByLabelText(/Monto origen/), '10');
    await user.type(screen.getByLabelText(/^Tasa/), '1');
    await user.click(screen.getByLabelText(/Método de pago \(egreso\)/));
    await user.click(await screen.findByRole('option', { name: 'Efectivo' }));
    await user.click(screen.getByLabelText(/Método de pago \(ingreso\)/));
    await user.click(await screen.findByRole('option', { name: 'Transferencia' }));
    await user.click(screen.getByRole('button', { name: 'Registrar operación' }));

    expect(
      await screen.findByText('La moneda destino debe ser distinta de la origen'),
    ).toBeInTheDocument();
    expect(tesoreriaService.crearOperacionCambio).not.toHaveBeenCalled();
  });
});
