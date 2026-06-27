import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/nominaService', () => ({
  nominaService: {
    getProceso: vi.fn(),
    getRecibosProceso: vi.fn(),
    getPeriodos: vi.fn(),
    procesarProceso: vi.fn(),
    aprobarProceso: vi.fn(),
    aprobarRecibo: vi.fn(),
    marcarReciboPagada: vi.fn(),
  },
}));

vi.mock('../services/rrhhService', () => ({
  rrhhService: {
    getEmpleadosDeEmpresa: vi.fn(),
  },
}));

import { nominaService } from '../services/nominaService';
import { rrhhService } from '../services/rrhhService';
import ProcesoNominaDetailPage from '../pages/Nomina/ProcesoNominaDetailPage';

/** Error como el que arma services/api.buildError: message JSON + status HTTP. */
function httpError(body: unknown, status: number): Error {
  const e = new Error(JSON.stringify(body)) as Error & { status?: number };
  e.status = status;
  return e;
}

const proceso = {
  id_proceso_nomina: 'proc-1',
  id_empresa: 'emp-1',
  id_periodo_nomina: 'per-1',
  numero_proceso: 'NOM-2026-06',
  fecha_proceso: '2026-06-12T10:00:00Z',
  total_empleados: 0,
  total_devengado: '0.0000',
  total_deducciones: '0.0000',
  total_neto: '0.0000',
  estado: 'EN_PROCESO',
  observaciones: null,
  fecha_creacion: '2026-06-12T09:00:00Z',
};

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

const empleados = [
  {
    id: 1,
    empresa: 'emp-1',
    referencia_externa: null,
    documento_json: { salario_mensual: '500.00' },
    nombre: 'Ana',
    apellido: 'Pérez',
    cedula: 'V-111',
    cargo: null,
    fecha_ingreso: '2024-01-15',
    activo: true,
    contacto: null,
  },
  {
    id: 2,
    empresa: 'emp-1',
    referencia_externa: null,
    documento_json: null,
    nombre: 'Luis',
    apellido: 'Gómez',
    cedula: 'V-222',
    cargo: null,
    fecha_ingreso: '2023-05-01',
    activo: true,
    contacto: null,
  },
  {
    id: 3,
    empresa: 'emp-1',
    referencia_externa: null,
    documento_json: null,
    nombre: 'Retirada',
    apellido: 'Inactiva',
    cedula: 'V-333',
    cargo: null,
    fecha_ingreso: '2020-01-01',
    activo: false,
    contacto: null,
  },
];

const recibos = [
  {
    id_nomina: 'nom-1',
    id_proceso_nomina: 'proc-1',
    id_empleado: 1,
    sueldo_base: '500.0000',
    total_devengado: '550.0000',
    total_deducciones: '30.2500',
    total_neto: '519.7500',
    dias_trabajados: 30,
    horas_trabajadas: '0.00',
    horas_extras: '4.00',
    estado: 'CALCULADA',
    fecha_calculo: '2026-06-12T10:00:00Z',
    observaciones: null,
  },
  {
    id_nomina: 'nom-2',
    id_proceso_nomina: 'proc-1',
    id_empleado: 3,
    sueldo_base: '950.0000',
    total_devengado: '950.0000',
    total_deducciones: '52.2500',
    total_neto: '897.7500',
    dias_trabajados: 30,
    horas_trabajadas: '0.00',
    horas_extras: '0.00',
    estado: 'CALCULADA',
    fecha_calculo: '2026-06-12T10:00:00Z',
    observaciones: null,
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/nomina/procesos/proc-1']}>
          <Routes>
            <Route path="/nomina/procesos/:id" element={<ProcesoNominaDetailPage />} />
            <Route path="/nomina/procesos" element={<div>lista-procesos</div>} />
            <Route path="/contabilidad/mapeos" element={<div>pagina-mapeos</div>} />
          </Routes>
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

async function abrirDialogoProcesar(user: ReturnType<typeof userEvent.setup>) {
  const boton = await screen.findByRole('button', { name: /^procesar$/i });
  await waitFor(() => expect(boton).toBeEnabled());
  await user.click(boton);
  return screen.findByRole('dialog');
}

describe('ProcesoNominaDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(nominaService.getProceso).mockResolvedValue(proceso);
    vi.mocked(nominaService.getRecibosProceso).mockResolvedValue([]);
    vi.mocked(nominaService.getPeriodos).mockResolvedValue([periodo]);
    vi.mocked(rrhhService.getEmpleadosDeEmpresa).mockResolvedValue(empleados);
  });

  afterEach(() => {
    cleanup();
  });

  it('muestra los recibos por empleado y el total neto sumado con decimal.js', async () => {
    vi.mocked(nominaService.getProceso).mockResolvedValue({
      ...proceso,
      estado: 'COMPLETADO',
      total_empleados: 2,
      total_devengado: '1500.0000',
      total_deducciones: '82.5000',
      total_neto: '1417.5000',
    });
    vi.mocked(nominaService.getRecibosProceso).mockResolvedValue(recibos);
    renderPage();

    expect(await screen.findByText(/NOM-2026-06/)).toBeInTheDocument();
    expect(await screen.findByText('Ana Pérez')).toBeInTheDocument();
    // El recibo de la empleada inactiva también se nombra (histórico).
    expect(screen.getByText('Retirada Inactiva')).toBeInTheDocument();
    expect(screen.getByText('519.75')).toBeInTheDocument();
    expect(screen.getByText('897.75')).toBeInTheDocument();
    // 519.7500 + 897.7500 sumado con decimal.js → 1417.50 exacto.
    expect(screen.getByText('Total neto: 1417.50')).toBeInTheDocument();
    // KPIs del proceso (strings decimales del backend formateados, no float).
    expect(screen.getByText('1500.00')).toBeInTheDocument();
    expect(screen.getByText('82.50')).toBeInTheDocument();
  });

  it('bloquea Procesar y avisa que los recibos son inmutables si no está EN_PROCESO', async () => {
    vi.mocked(nominaService.getProceso).mockResolvedValue({ ...proceso, estado: 'COMPLETADO' });
    vi.mocked(nominaService.getRecibosProceso).mockResolvedValue(recibos);
    renderPage();
    await screen.findByText(/NOM-2026-06/);
    expect(screen.getByRole('button', { name: /^procesar$/i })).toBeDisabled();
    expect(screen.getByText(/los recibos emitidos son inmutables/i)).toBeInTheDocument();
  });

  it('procesa con datos variables por empleado: horas extra y bono nocturno como strings', async () => {
    vi.mocked(nominaService.procesarProceso).mockResolvedValue({
      ...proceso,
      estado: 'COMPLETADO',
      total_neto: '1417.5000',
      asiento_contable: 'as-1',
    });
    const user = userEvent.setup();
    renderPage();
    const dialogo = await abrirDialogoProcesar(user);

    // Solo empleados activos en el formulario (la inactiva no se procesa).
    expect(within(dialogo).getByText(/Ana Pérez \(V-111\)/)).toBeInTheDocument();
    expect(within(dialogo).getByText(/Luis Gómez \(V-222\)/)).toBeInTheDocument();
    expect(within(dialogo).queryByText(/Retirada Inactiva/)).not.toBeInTheDocument();
    // Luis no tiene salario en documento_json: se advierte (usará salario mínimo).
    expect(within(dialogo).getByText(/sin salario definido/i)).toBeInTheDocument();

    // Ana: 4 h extra diurnas + bono nocturno con 8 h nocturnas.
    await user.type(within(dialogo).getAllByLabelText(/horas extra diurnas/i)[0], '4');
    await user.click(within(dialogo).getAllByLabelText(/bono nocturno/i)[0]);
    await user.type(await within(dialogo).findByLabelText(/^horas nocturnas/i), '8');
    // Luis: 2.5 h extra nocturnas.
    await user.type(within(dialogo).getAllByLabelText(/horas extra nocturnas/i)[1], '2.5');

    await user.click(within(dialogo).getByRole('button', { name: /procesar nómina/i }));

    await waitFor(() =>
      expect(nominaService.procesarProceso).toHaveBeenCalledWith('proc-1', {
        '1': { horas_extra_diurnas: '4', horas_nocturnas: '8' },
        '2': { horas_extra_nocturnas: '2.5' },
      }),
    );
    // Feedback del resultado con el neto exacto.
    expect(await screen.findByText(/nómina procesada\. total neto: 1417\.50/i)).toBeInTheDocument();
  });

  it('procesa sin datos (vacío): todos los empleados con defaults del motor', async () => {
    vi.mocked(nominaService.procesarProceso).mockResolvedValue({
      ...proceso,
      estado: 'COMPLETADO',
      total_neto: '950.0000',
      asiento_contable: null,
      advertencia_asiento: 'No hay MapeoContable activo para empresa=emp-1, tipo=NOMINA.',
    });
    const user = userEvent.setup();
    renderPage();
    const dialogo = await abrirDialogoProcesar(user);

    await user.click(within(dialogo).getByRole('button', { name: /procesar nómina/i }));

    await waitFor(() => expect(nominaService.procesarProceso).toHaveBeenCalledWith('proc-1', {}));
    // Contabilidad inactiva sin mapeo: advertencia visible, el proceso quedó OK.
    expect(await screen.findByText(/no hay mapeocontable activo/i)).toBeInTheDocument();
  });

  it('422 sin mapeo NOMINA: muestra la alerta con link a /contabilidad/mapeos', async () => {
    vi.mocked(nominaService.procesarProceso).mockRejectedValue(
      httpError(
        {
          error:
            'Configure el Mapeo Contable antes de continuar (contabilidad activa, NOMINA): ' +
            'No hay MapeoContable activo para empresa=emp-1, tipo=NOMINA.',
        },
        422,
      ),
    );
    const user = userEvent.setup();
    renderPage();
    const dialogo = await abrirDialogoProcesar(user);
    await user.click(within(dialogo).getByRole('button', { name: /procesar nómina/i }));

    expect(
      await within(dialogo).findByText(/falta el mapeo contable NOMINA/i),
    ).toBeInTheDocument();
    expect(within(dialogo).getByText(/configure el mapeo contable antes de continuar/i)).toBeInTheDocument();

    await user.click(within(dialogo).getByRole('button', { name: /configurar mapeos/i }));
    expect(await screen.findByText('pagina-mapeos')).toBeInTheDocument();
  });

  it('400 de re-proceso: muestra el error de recibos inmutables sin link a mapeos', async () => {
    vi.mocked(nominaService.procesarProceso).mockRejectedValue(
      httpError(
        {
          error:
            'El proceso está en estado COMPLETADO; solo se procesan procesos EN_PROCESO. ' +
            'Para recalcular, cancele este proceso y cree uno nuevo.',
        },
        400,
      ),
    );
    const user = userEvent.setup();
    renderPage();
    const dialogo = await abrirDialogoProcesar(user);
    await user.click(within(dialogo).getByRole('button', { name: /procesar nómina/i }));

    expect(
      await within(dialogo).findByText(/el proceso está en estado COMPLETADO/i),
    ).toBeInTheDocument();
    expect(
      within(dialogo).queryByRole('button', { name: /configurar mapeos/i }),
    ).not.toBeInTheDocument();
    expect(nominaService.procesarProceso).toHaveBeenCalledTimes(1);
  });

  it('valida que el bono nocturno exija horas nocturnas > 0 antes de enviar', async () => {
    const user = userEvent.setup();
    renderPage();
    const dialogo = await abrirDialogoProcesar(user);

    await user.click(within(dialogo).getAllByLabelText(/bono nocturno/i)[0]);
    await user.click(within(dialogo).getByRole('button', { name: /procesar nómina/i }));

    expect(
      await within(dialogo).findByText(/indique las horas nocturnas \(> 0\) para aplicar el bono/i),
    ).toBeInTheDocument();
    expect(nominaService.procesarProceso).not.toHaveBeenCalled();
  });

  it('muestra el vacío de recibos mientras el proceso está EN_PROCESO', async () => {
    renderPage();
    expect(
      await screen.findByText(/aún no hay recibos: procese la nómina para generarlos/i),
    ).toBeInTheDocument();
  });

  it('aprueba el proceso COMPLETADO desde el botón de cabecera', async () => {
    vi.mocked(nominaService.getProceso).mockResolvedValue({ ...proceso, estado: 'COMPLETADO' });
    vi.mocked(nominaService.getRecibosProceso).mockResolvedValue(recibos);
    vi.mocked(nominaService.aprobarProceso).mockResolvedValue({ ...proceso, estado: 'APROBADO' });
    const user = userEvent.setup();
    renderPage();

    const boton = await screen.findByRole('button', { name: /aprobar proceso/i });
    await user.click(boton);

    await waitFor(() => expect(nominaService.aprobarProceso).toHaveBeenCalledWith('proc-1'));
    expect(await screen.findByText(/proceso de nómina aprobado/i)).toBeInTheDocument();
  });

  it('no muestra el botón de aprobar proceso si no está COMPLETADO', async () => {
    renderPage();
    await screen.findByText(/NOM-2026-06/);
    expect(screen.queryByRole('button', { name: /aprobar proceso/i })).not.toBeInTheDocument();
  });

  it('aprueba un recibo CALCULADA desde la fila', async () => {
    vi.mocked(nominaService.getProceso).mockResolvedValue({ ...proceso, estado: 'APROBADO' });
    vi.mocked(nominaService.getRecibosProceso).mockResolvedValue([recibos[0]]);
    vi.mocked(nominaService.aprobarRecibo).mockResolvedValue({ ...recibos[0], estado: 'APROBADA' });
    const user = userEvent.setup();
    renderPage();

    const fila = await screen.findByText('Ana Pérez');
    const filaRow = fila.closest('tr')!;
    await user.click(within(filaRow).getByRole('button', { name: /^aprobar$/i }));

    await waitFor(() => expect(nominaService.aprobarRecibo).toHaveBeenCalledWith('nom-1'));
    expect(await screen.findByText(/recibo aprobado/i)).toBeInTheDocument();
  });

  it('marca un recibo APROBADA como pagado desde la fila', async () => {
    vi.mocked(nominaService.getProceso).mockResolvedValue({ ...proceso, estado: 'APROBADO' });
    vi.mocked(nominaService.getRecibosProceso).mockResolvedValue([
      { ...recibos[0], estado: 'APROBADA' },
    ]);
    vi.mocked(nominaService.marcarReciboPagada).mockResolvedValue({
      ...recibos[0],
      estado: 'PAGADA',
    });
    const user = userEvent.setup();
    renderPage();

    const fila = await screen.findByText('Ana Pérez');
    const filaRow = fila.closest('tr')!;
    await user.click(within(filaRow).getByRole('button', { name: /marcar pagada/i }));

    await waitFor(() => expect(nominaService.marcarReciboPagada).toHaveBeenCalledWith('nom-1'));
    expect(await screen.findByText(/recibo marcado como pagado/i)).toBeInTheDocument();
  });
});
