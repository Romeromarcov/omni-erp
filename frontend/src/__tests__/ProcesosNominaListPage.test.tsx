import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/nominaService', () => ({
  nominaService: {
    getProcesosPaginated: vi.fn(),
    getPeriodos: vi.fn(),
    crearProceso: vi.fn(),
    crearPeriodo: vi.fn(),
  },
}));

import { nominaService } from '../services/nominaService';
import ProcesosNominaListPage from '../pages/Nomina/ProcesosNominaListPage';

const periodo = {
  id_periodo_nomina: 'per-1',
  id_empresa: 'emp-1',
  nombre_periodo: 'Junio 2026',
  fecha_inicio: '2026-06-01',
  fecha_fin: '2026-06-30',
  fecha_pago: '2026-06-30',
  tipo_periodo: 'MENSUAL',
  estado: 'ABIERTO',
  observaciones: null,
  activo: true,
  fecha_creacion: '2026-06-01T00:00:00Z',
};

const periodoAjeno = {
  ...periodo,
  id_periodo_nomina: 'per-ajeno',
  id_empresa: 'emp-OTRA',
  nombre_periodo: 'Periodo Ajeno',
};

const proceso = {
  id_proceso_nomina: 'proc-1',
  id_empresa: 'emp-1',
  id_periodo_nomina: 'per-1',
  numero_proceso: 'NOM-2026-06',
  fecha_proceso: '2026-06-12T10:00:00Z',
  total_empleados: 2,
  total_devengado: '1500.0000',
  total_deducciones: '82.5000',
  total_neto: '1417.5000',
  estado: 'COMPLETADO',
  observaciones: null,
  fecha_creacion: '2026-06-12T09:00:00Z',
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/nomina/procesos']}>
          <Routes>
            <Route path="/nomina/procesos" element={<ProcesosNominaListPage />} />
            <Route path="/nomina/procesos/:id" element={<div>detalle-proceso</div>} />
          </Routes>
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('ProcesosNominaListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    vi.mocked(nominaService.getProcesosPaginated).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [proceso],
    });
    vi.mocked(nominaService.getPeriodos).mockResolvedValue([periodo, periodoAjeno]);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('muestra los procesos con período resuelto, neto decimal y estado', async () => {
    renderPage();
    expect(await screen.findByText('NOM-2026-06')).toBeInTheDocument();
    expect(await screen.findByText('Junio 2026')).toBeInTheDocument();
    expect(screen.getByText('1417.50')).toBeInTheDocument();
    expect(screen.getByText('COMPLETADO')).toBeInTheDocument();
    expect(screen.getByText('2026-06-12')).toBeInTheDocument();
  });

  it('crea un proceso para un período de la empresa activa y navega al detalle', async () => {
    vi.mocked(nominaService.crearProceso).mockResolvedValue({
      ...proceso,
      id_proceso_nomina: 'proc-nuevo',
      estado: 'EN_PROCESO',
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('NOM-2026-06');

    await user.click(screen.getByRole('button', { name: /nuevo proceso/i }));
    const dialogo = await screen.findByRole('dialog');
    await user.click(within(dialogo).getByLabelText(/período/i));
    // El select solo ofrece períodos de la empresa activa (R-CODE-1).
    expect(screen.queryByRole('option', { name: /periodo ajeno/i })).not.toBeInTheDocument();
    await user.click(await screen.findByRole('option', { name: /junio 2026/i }));
    await user.type(within(dialogo).getByLabelText(/número/i), 'NOM-2026-07');
    await user.click(within(dialogo).getByRole('button', { name: /crear proceso/i }));

    await waitFor(() =>
      expect(nominaService.crearProceso).toHaveBeenCalledWith({
        id_empresa: 'emp-1',
        id_periodo_nomina: 'per-1',
        numero_proceso: 'NOM-2026-07',
        fecha_proceso: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T/),
      }),
    );
    expect(await screen.findByText('detalle-proceso')).toBeInTheDocument();
  });

  it('muestra el 400 del backend al crear proceso (número duplicado)', async () => {
    vi.mocked(nominaService.crearProceso).mockRejectedValue(
      new Error(
        JSON.stringify({
          non_field_errors: ['Los campos id_empresa, numero_proceso deben formar un conjunto único.'],
        }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('NOM-2026-06');

    await user.click(screen.getByRole('button', { name: /nuevo proceso/i }));
    const dialogo = await screen.findByRole('dialog');
    await user.click(within(dialogo).getByLabelText(/período/i));
    await user.click(await screen.findByRole('option', { name: /junio 2026/i }));
    await user.type(within(dialogo).getByLabelText(/número/i), 'NOM-2026-06');
    await user.click(within(dialogo).getByRole('button', { name: /crear proceso/i }));

    expect(
      await screen.findByText(/deben formar un conjunto único/i),
    ).toBeInTheDocument();
  });

  it('crea un período con tipo y fechas validadas', async () => {
    vi.mocked(nominaService.crearPeriodo).mockResolvedValue({
      ...periodo,
      id_periodo_nomina: 'per-2',
      nombre_periodo: 'Julio 2026',
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('NOM-2026-06');

    await user.click(screen.getByRole('button', { name: /nuevo período/i }));
    const dialogo = await screen.findByRole('dialog');
    await user.type(within(dialogo).getByLabelText(/nombre del período/i), 'Julio 2026');
    await user.type(within(dialogo).getByLabelText(/fecha de inicio/i), '2026-07-01');
    await user.type(within(dialogo).getByLabelText(/fecha de fin/i), '2026-07-31');
    await user.type(within(dialogo).getByLabelText(/fecha de pago/i), '2026-07-31');
    await user.click(within(dialogo).getByRole('button', { name: /crear período/i }));

    await waitFor(() =>
      expect(nominaService.crearPeriodo).toHaveBeenCalledWith({
        id_empresa: 'emp-1',
        nombre_periodo: 'Julio 2026',
        tipo_periodo: 'MENSUAL',
        fecha_inicio: '2026-07-01',
        fecha_fin: '2026-07-31',
        fecha_pago: '2026-07-31',
      }),
    );
  });

  it('rechaza un período con fecha fin anterior al inicio sin llamar a la API', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('NOM-2026-06');

    await user.click(screen.getByRole('button', { name: /nuevo período/i }));
    const dialogo = await screen.findByRole('dialog');
    await user.type(within(dialogo).getByLabelText(/nombre del período/i), 'Inválido');
    await user.type(within(dialogo).getByLabelText(/fecha de inicio/i), '2026-07-31');
    await user.type(within(dialogo).getByLabelText(/fecha de fin/i), '2026-07-01');
    await user.type(within(dialogo).getByLabelText(/fecha de pago/i), '2026-07-31');
    await user.click(within(dialogo).getByRole('button', { name: /crear período/i }));

    expect(
      await screen.findByText(/la fecha de fin debe ser posterior o igual a la de inicio/i),
    ).toBeInTheDocument();
    expect(nominaService.crearPeriodo).not.toHaveBeenCalled();
  });

  it('muestra el vacío cuando no hay procesos', async () => {
    vi.mocked(nominaService.getProcesosPaginated).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    renderPage();
    expect(await screen.findByText(/no hay procesos de nómina registrados/i)).toBeInTheDocument();
  });
});
