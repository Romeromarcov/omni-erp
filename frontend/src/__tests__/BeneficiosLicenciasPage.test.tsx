import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));

import { get, post, patch, del } from '../services/api';
import BeneficiosLicenciasPage from '../pages/RRHH/BeneficiosLicenciasPage';

const empleados = [
  {
    id: 7,
    empresa: 'e1',
    nombre: 'Ana',
    apellido: 'Pérez',
    cedula: 'V-1',
    cargo: null,
    fecha_ingreso: '2025-01-01',
    activo: true,
    referencia_externa: null,
    documento_json: null,
    contacto: null,
  },
];

const beneficio = {
  id_beneficio: 'b1',
  id_empresa: 'e1',
  nombre_beneficio: 'Bono Alimentación',
  descripcion: 'Cestaticket',
  tipo_beneficio: 'ALIMENTACION',
  monto_fijo: '100.0000',
  porcentaje_salario: null,
  es_obligatorio: false,
  activo: true,
};

const asignacion = {
  id_beneficio_empleado: 'a1',
  id_empleado: 7,
  id_beneficio: 'b1',
  fecha_inicio: '2026-06-01',
  fecha_fin: null,
  monto_personalizado: null,
  porcentaje_personalizado: null,
  estado: 'ACTIVO',
  observaciones: null,
};

const tipoLicencia = {
  id_tipo_licencia: 't1',
  id_empresa: 'e1',
  nombre_tipo: 'Vacaciones',
  descripcion: null,
  es_remunerada: true,
  dias_maximos_por_año: 15,
  requiere_aprobacion: true,
  activo: true,
};

const licenciaPendiente = {
  id_licencia: 'l1',
  id_empleado: 7,
  id_tipo_licencia: 't1',
  fecha_inicio: '2026-06-10',
  fecha_fin: '2026-06-14',
  dias_solicitados: 5,
  motivo: 'Descanso',
  estado: 'PENDIENTE',
  id_aprobador: null,
  fecha_aprobacion: null,
  observaciones_aprobacion: null,
};
const licenciaAprobada = {
  ...licenciaPendiente,
  id_licencia: 'l2',
  fecha_inicio: '2026-05-01',
  estado: 'APROBADA',
};

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/rrhh/empleados')) {
      return Promise.resolve({ count: 1, next: null, previous: null, results: empleados });
    }
    if (url.startsWith('/rrhh/beneficios-empleado')) return Promise.resolve([asignacion]);
    if (url.startsWith('/rrhh/beneficios')) return Promise.resolve([beneficio]);
    if (url.startsWith('/rrhh/tipos-licencia')) return Promise.resolve([tipoLicencia]);
    if (url.startsWith('/rrhh/licencias-empleado'))
      return Promise.resolve([licenciaPendiente, licenciaAprobada]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <BeneficiosLicenciasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const irAPestana = (nombre: string) => fireEvent.click(screen.getByRole('tab', { name: nombre }));

describe('BeneficiosLicenciasPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('renderiza el encabezado y la primera pestaña', async () => {
    renderPage();
    expect(
      screen.getByRole('heading', { name: 'Beneficios y Licencias' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Bono Alimentación')).toBeInTheDocument();
  });

  // ── Beneficios ────────────────────────────────────────────────────────────────

  it('crea un beneficio enviando el payload whitelisteado', async () => {
    vi.mocked(post).mockResolvedValue(beneficio);
    renderPage();
    await screen.findByText('Bono Alimentación');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo beneficio' }));
    fireEvent.change(screen.getByLabelText(/Nombre del beneficio/), {
      target: { value: 'HCM' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/rrhh/beneficios/',
        expect.objectContaining({
          id_empresa: 'e1',
          nombre_beneficio: 'HCM',
          tipo_beneficio: 'MONETARIO',
          es_obligatorio: false,
          activo: true,
        }),
      ),
    );
  });

  it('valida el nombre requerido al crear un beneficio', async () => {
    renderPage();
    await screen.findByText('Bono Alimentación');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo beneficio' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique el nombre del beneficio/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('edita un beneficio existente (PATCH)', async () => {
    vi.mocked(patch).mockResolvedValue(beneficio);
    renderPage();
    await screen.findByText('Bono Alimentación');
    const fila = screen.getByText('Bono Alimentación').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    fireEvent.change(screen.getByLabelText(/Monto fijo/), { target: { value: '150' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/rrhh/beneficios/b1/',
        expect.objectContaining({ monto_fijo: '150' }),
      ),
    );
  });

  it('elimina un beneficio con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Bono Alimentación');
    const fila = screen.getByText('Bono Alimentación').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/rrhh/beneficios/b1/'));
    confirmSpy.mockRestore();
  });

  it('muestra el error del backend al crear un beneficio', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ detail: 'duplicado' })));
    renderPage();
    await screen.findByText('Bono Alimentación');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo beneficio' }));
    fireEvent.change(screen.getByLabelText(/Nombre del beneficio/), {
      target: { value: 'HCM' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/duplicado/)).toBeInTheDocument();
  });

  // ── Asignaciones ──────────────────────────────────────────────────────────────

  it('crea una asignación de beneficio enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue(asignacion);
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Asignaciones');
    await screen.findByRole('button', { name: 'Nueva asignación' });
    fireEvent.click(screen.getByRole('button', { name: 'Nueva asignación' }));

    fireEvent.mouseDown(within(screen.getByRole('dialog')).getByLabelText(/Empleado/));
    fireEvent.click(await screen.findByRole('option', { name: /Ana Pérez/ }));
    fireEvent.mouseDown(within(screen.getByRole('dialog')).getByLabelText(/Beneficio/));
    fireEvent.click(await screen.findByRole('option', { name: 'Bono Alimentación' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/rrhh/beneficios-empleado/',
        expect.objectContaining({ id_empleado: 7, id_beneficio: 'b1', estado: 'ACTIVO' }),
      ),
    );
  });

  it('valida campos requeridos al crear una asignación', async () => {
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Asignaciones');
    fireEvent.click(await screen.findByRole('button', { name: 'Nueva asignación' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Seleccione empleado, beneficio y fecha de inicio/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('filtra asignaciones por empleado (client-side)', async () => {
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Asignaciones');
    await screen.findByLabelText('Filtrar por empleado');
    fireEvent.mouseDown(screen.getByLabelText('Filtrar por empleado'));
    fireEvent.click(await screen.findByRole('option', { name: /Ana Pérez/ }));
    await waitFor(() => expect(screen.getByText('Bono Alimentación')).toBeInTheDocument());
  });

  it('elimina una asignación con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Asignaciones');
    const fila = (await screen.findByText('Ana Pérez')).closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/rrhh/beneficios-empleado/a1/'));
    confirmSpy.mockRestore();
  });

  // ── Tipos de Licencia ─────────────────────────────────────────────────────────

  it('crea un tipo de licencia enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue(tipoLicencia);
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Tipos de Licencia');
    await screen.findByText('Vacaciones');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo tipo de licencia' }));
    fireEvent.change(screen.getByLabelText(/Nombre del tipo/), { target: { value: 'Reposo' } });
    fireEvent.change(screen.getByLabelText(/Días máximos por año/), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/rrhh/tipos-licencia/',
        expect.objectContaining({
          id_empresa: 'e1',
          nombre_tipo: 'Reposo',
          dias_maximos_por_año: 30,
          es_remunerada: true,
        }),
      ),
    );
  });

  it('valida el nombre requerido al crear un tipo de licencia', async () => {
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Tipos de Licencia');
    fireEvent.click(await screen.findByRole('button', { name: 'Nuevo tipo de licencia' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique el nombre del tipo/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('elimina un tipo de licencia con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Tipos de Licencia');
    const fila = (await screen.findByText('Vacaciones')).closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/rrhh/tipos-licencia/t1/'));
    confirmSpy.mockRestore();
  });

  // ── Licencias ───────────────────────────────────────────────────────────────

  it('crea una licencia con estado inicial PENDIENTE', async () => {
    vi.mocked(post).mockResolvedValue(licenciaPendiente);
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Licencias');
    await screen.findByRole('button', { name: 'Nueva licencia' });
    fireEvent.click(screen.getByRole('button', { name: 'Nueva licencia' }));

    fireEvent.mouseDown(within(screen.getByRole('dialog')).getByLabelText(/Empleado/));
    fireEvent.click(await screen.findByRole('option', { name: /Ana Pérez/ }));
    fireEvent.mouseDown(within(screen.getByRole('dialog')).getByLabelText(/Tipo de licencia/));
    fireEvent.click(await screen.findByRole('option', { name: 'Vacaciones' }));
    fireEvent.change(within(screen.getByRole('dialog')).getByLabelText(/Días solicitados/), {
      target: { value: '5' },
    });
    fireEvent.change(within(screen.getByRole('dialog')).getByLabelText(/Motivo/), {
      target: { value: 'Viaje' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/rrhh/licencias-empleado/',
        expect.objectContaining({
          id_empleado: 7,
          id_tipo_licencia: 't1',
          dias_solicitados: 5,
          motivo: 'Viaje',
          estado: 'PENDIENTE',
        }),
      ),
    );
  });

  it('valida campos requeridos al crear una licencia', async () => {
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Licencias');
    fireEvent.click(await screen.findByRole('button', { name: 'Nueva licencia' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Seleccione empleado, tipo de licencia y fechas/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('aprueba una licencia PENDIENTE vía PATCH; deshabilita acciones en una APROBADA', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(patch).mockResolvedValue({ ...licenciaPendiente, estado: 'APROBADA' });
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Licencias');

    const filaPend = (await screen.findByText('2026-06-10')).closest('tr')!;
    expect(within(filaPend).getByRole('button', { name: 'Aprobar' })).toBeEnabled();

    const filaApr = screen.getByText('2026-05-01').closest('tr')!;
    expect(within(filaApr).getByRole('button', { name: 'Aprobar' })).toBeDisabled();
    expect(within(filaApr).getByRole('button', { name: 'Rechazar' })).toBeDisabled();

    fireEvent.click(within(filaPend).getByRole('button', { name: 'Aprobar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/rrhh/licencias-empleado/l1/', { estado: 'APROBADA' }),
    );
    confirmSpy.mockRestore();
  });

  it('rechaza una licencia PENDIENTE vía PATCH', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(patch).mockResolvedValue({ ...licenciaPendiente, estado: 'RECHAZADA' });
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Licencias');
    const filaPend = (await screen.findByText('2026-06-10')).closest('tr')!;
    fireEvent.click(within(filaPend).getByRole('button', { name: 'Rechazar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/rrhh/licencias-empleado/l1/', { estado: 'RECHAZADA' }),
    );
    confirmSpy.mockRestore();
  });

  it('filtra licencias por estado de revisión', async () => {
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Licencias');
    await screen.findByLabelText('Estado');
    fireEvent.mouseDown(screen.getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'Aprobada' }));
    // Tras filtrar por APROBADA queda solo la licencia aprobada (inicio 01/05)...
    expect(await screen.findByText('2026-05-01')).toBeInTheDocument();
    // ...y la pendiente (inicio 10/06) desaparece.
    await waitFor(() => expect(screen.queryByText('2026-06-10')).not.toBeInTheDocument());
  });

  it('elimina una licencia con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Licencias');
    const fila = (await screen.findByText('2026-06-10')).closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/rrhh/licencias-empleado/l1/'));
    confirmSpy.mockRestore();
  });

  it('muestra el error del backend al aprobar una licencia', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(patch).mockRejectedValue(new Error(JSON.stringify({ error: 'transición inválida' })));
    renderPage();
    await screen.findByText('Bono Alimentación');
    irAPestana('Licencias');
    const filaPend = (await screen.findByText('2026-06-10')).closest('tr')!;
    fireEvent.click(within(filaPend).getByRole('button', { name: 'Aprobar' }));
    expect(await screen.findByText(/transición inválida/)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });
});
