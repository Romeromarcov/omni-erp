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
import ControlAsistenciaPage from '../pages/ControlAsistencia/ControlAsistenciaPage';

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

const horario = {
  id_horario: 'h1',
  id_empresa: 'e1',
  nombre_horario: 'Diurno',
  descripcion: 'Lun-Vie',
  total_horas_semanales: '40.00',
  activo: true,
};
const horarioInactivo = { ...horario, id_horario: 'h2', nombre_horario: 'Nocturno', activo: false };

const asignacion = {
  id_asignacion_horario: 'a1',
  id_empleado: 7,
  id_horario: 'h1',
  fecha_inicio: '2026-06-01',
  fecha_fin: null,
  activo: true,
};

const registro = {
  id_registro_asistencia: 'r1',
  id_empleado: 7,
  fecha_hora_marcado: '2026-06-24T08:00:00Z',
  tipo_marcado: 'ENTRADA',
  metodo_marcado: 'WEB',
};

const resumenPendiente = {
  id_resumen_diario: 's1',
  id_empleado: 7,
  fecha: '2026-06-24',
  horas_trabajadas_netas: '8.00',
  horas_extras_normal: '0.00',
  horas_extras_feriado: '0.00',
  minutos_tardanza: 5,
  es_ausencia: false,
  estado_revision: 'PENDIENTE',
};
const resumenAprobado = {
  ...resumenPendiente,
  id_resumen_diario: 's2',
  fecha: '2026-06-23',
  estado_revision: 'APROBADO',
};

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/rrhh/empleados')) {
      return Promise.resolve({ count: 1, next: null, previous: null, results: empleados });
    }
    if (url.includes('/horarios-trabajo/activos/')) return Promise.resolve([horario]);
    if (url.startsWith('/control-asistencia/horarios-trabajo'))
      return Promise.resolve([horario, horarioInactivo]);
    if (url.includes('/asignaciones-horario/por_empleado/')) return Promise.resolve([asignacion]);
    if (url.startsWith('/control-asistencia/asignaciones-horario'))
      return Promise.resolve([asignacion]);
    if (url.includes('/registros-asistencia/hoy/')) return Promise.resolve([registro]);
    if (url.includes('/registros-asistencia/por_empleado_fecha/'))
      return Promise.resolve([registro]);
    if (url.startsWith('/control-asistencia/registros-asistencia'))
      return Promise.resolve([registro]);
    if (url.startsWith('/control-asistencia/resumenes-asistencia-diario'))
      return Promise.resolve([resumenPendiente, resumenAprobado]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ControlAsistenciaPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const irAPestana = (nombre: string) => fireEvent.click(screen.getByRole('tab', { name: nombre }));

describe('ControlAsistenciaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('renderiza el encabezado y las pestañas', async () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'Control de Asistencia' })).toBeInTheDocument();
    expect(await screen.findByText('Diurno')).toBeInTheDocument();
  });

  // ── Horarios ────────────────────────────────────────────────────────────────

  it('crea un horario enviando el payload whitelisteado', async () => {
    vi.mocked(post).mockResolvedValue(horario);
    renderPage();
    await screen.findByText('Diurno');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo horario' }));
    fireEvent.change(screen.getByLabelText(/Nombre del horario/), {
      target: { value: 'Mixto' },
    });
    fireEvent.change(screen.getByLabelText(/Total de horas semanales/), {
      target: { value: '44' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/', {
        id_empresa: 'e1',
        nombre_horario: 'Mixto',
        descripcion: null,
        dias_semana_json: null,
        total_horas_semanales: '44',
      }),
    );
  });

  it('valida campos requeridos al crear un horario', async () => {
    renderPage();
    await screen.findByText('Diurno');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo horario' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique el nombre y el total de horas/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('edita un horario existente (PATCH)', async () => {
    vi.mocked(patch).mockResolvedValue(horario);
    renderPage();
    await screen.findByText('Diurno');
    const fila = screen.getByText('Diurno').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    fireEvent.change(screen.getByLabelText(/Descripción/), { target: { value: 'Actualizado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/control-asistencia/horarios-trabajo/h1/',
        expect.objectContaining({ descripcion: 'Actualizado' }),
      ),
    );
  });

  it('desactiva un horario activo con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ ...horario, activo: false });
    renderPage();
    await screen.findByText('Diurno');
    const fila = screen.getByText('Diurno').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Desactivar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/h1/desactivar/', {}),
    );
    confirmSpy.mockRestore();
  });

  it('el botón Desactivar está deshabilitado para un horario inactivo', async () => {
    renderPage();
    await screen.findByText('Nocturno');
    const fila = screen.getByText('Nocturno').closest('tr')!;
    expect(within(fila).getByRole('button', { name: 'Desactivar' })).toBeDisabled();
  });

  it('no desactiva si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('Diurno');
    const fila = screen.getByText('Diurno').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Desactivar' }));
    expect(post).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('elimina un horario con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Diurno');
    const fila = screen.getByText('Diurno').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/h1/'),
    );
    confirmSpy.mockRestore();
  });

  it('muestra el error del backend al desactivar', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockRejectedValue(
      new Error(JSON.stringify({ error: 'Hay 2 asignaciones activas' })),
    );
    renderPage();
    await screen.findByText('Diurno');
    const fila = screen.getByText('Diurno').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Desactivar' }));
    expect(await screen.findByText(/asignaciones activas/)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  // ── Asignaciones ──────────────────────────────────────────────────────────────

  it('crea una asignación enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue(asignacion);
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Asignaciones');
    await screen.findByRole('button', { name: 'Nueva asignación' });
    fireEvent.click(screen.getByRole('button', { name: 'Nueva asignación' }));

    fireEvent.mouseDown(within(screen.getByRole('dialog')).getByLabelText(/Empleado/));
    fireEvent.click(await screen.findByRole('option', { name: /Ana Pérez/ }));
    fireEvent.mouseDown(within(screen.getByRole('dialog')).getByLabelText(/Horario/));
    fireEvent.click(await screen.findByRole('option', { name: 'Diurno' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/control-asistencia/asignaciones-horario/',
        expect.objectContaining({ id_empleado: 7, id_horario: 'h1', fecha_fin: null }),
      ),
    );
  });

  it('valida campos requeridos al crear una asignación', async () => {
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Asignaciones');
    fireEvent.click(await screen.findByRole('button', { name: 'Nueva asignación' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Seleccione empleado, horario y fecha de inicio/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('filtra asignaciones por empleado usando por_empleado', async () => {
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Asignaciones');
    await screen.findByLabelText('Filtrar por empleado');
    fireEvent.mouseDown(screen.getByLabelText('Filtrar por empleado'));
    fireEvent.click(await screen.findByRole('option', { name: /Ana Pérez/ }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        '/control-asistencia/asignaciones-horario/por_empleado/?empleado_id=7',
      ),
    );
  });

  it('finaliza una asignación activa con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ ...asignacion, activo: false });
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Asignaciones');
    const fila = (await screen.findByText('Ana Pérez')).closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Finalizar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/control-asistencia/asignaciones-horario/a1/finalizar/',
        {},
      ),
    );
    confirmSpy.mockRestore();
  });

  it('elimina una asignación con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Asignaciones');
    const fila = (await screen.findByText('Ana Pérez')).closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/control-asistencia/asignaciones-horario/a1/'),
    );
    confirmSpy.mockRestore();
  });

  it('edita una asignación (PATCH)', async () => {
    vi.mocked(patch).mockResolvedValue(asignacion);
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Asignaciones');
    const fila = (await screen.findByText('Ana Pérez')).closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    fireEvent.change(within(screen.getByRole('dialog')).getByLabelText(/Fecha de fin/), {
      target: { value: '2026-12-31' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/control-asistencia/asignaciones-horario/a1/',
        expect.objectContaining({ fecha_fin: '2026-12-31' }),
      ),
    );
  });

  // ── Registros ─────────────────────────────────────────────────────────────────

  it('exige un empleado para marcar asistencia', async () => {
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Registros');
    await screen.findByRole('button', { name: 'Marcar asistencia' });
    fireEvent.click(screen.getByRole('button', { name: 'Marcar asistencia' }));
    expect(await screen.findByText(/Seleccione un empleado para marcar/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('marca asistencia para el empleado seleccionado', async () => {
    vi.mocked(post).mockResolvedValue(registro);
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Registros');
    await screen.findByLabelText('Empleado');
    fireEvent.mouseDown(screen.getByLabelText('Empleado'));
    fireEvent.click(await screen.findByRole('option', { name: /Ana Pérez/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Marcar asistencia' }));

    // Cambia el tipo de marcado a SALIDA dentro del diálogo.
    fireEvent.mouseDown(within(screen.getByRole('dialog')).getByLabelText(/Tipo de marcado/));
    fireEvent.click(await screen.findByRole('option', { name: 'Salida' }));
    fireEvent.click(screen.getByRole('button', { name: 'Registrar marcaje' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/control-asistencia/registros-asistencia/marcar_asistencia/',
        { empleado_id: '7', tipo_marcado: 'SALIDA', metodo_marcado: 'WEB' },
      ),
    );
  });

  it('alterna a la vista "Hoy" y consulta el endpoint hoy/', async () => {
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Registros');
    fireEvent.click(await screen.findByRole('button', { name: 'Ver hoy' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/hoy/'),
    );
    expect(screen.getByRole('button', { name: 'Viendo: Hoy' })).toBeInTheDocument();
  });

  it('al seleccionar empleado consulta por_empleado_fecha', async () => {
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Registros');
    await screen.findByLabelText('Empleado');
    fireEvent.mouseDown(screen.getByLabelText('Empleado'));
    fireEvent.click(await screen.findByRole('option', { name: /Ana Pérez/ }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        '/control-asistencia/registros-asistencia/por_empleado_fecha/?empleado_id=7',
      ),
    );
  });

  it('elimina un registro con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Registros');
    const fila = (await screen.findByText('Entrada')).closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/r1/'),
    );
    confirmSpy.mockRestore();
  });

  // ── Resúmenes ───────────────────────────────────────────────────────────────

  it('genera resúmenes y muestra el mensaje de éxito', async () => {
    vi.mocked(post).mockResolvedValue({ mensaje: 'Se generaron 3 resúmenes diarios', fecha: 'hoy' });
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Resúmenes');
    fireEvent.click(await screen.findByRole('button', { name: 'Generar resúmenes' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        expect.stringContaining('/generar_resumen_diario/'),
        expect.objectContaining({ fecha: expect.any(String) }),
      ),
    );
    expect(await screen.findByText(/Se generaron 3 resúmenes/)).toBeInTheDocument();
  });

  it('aprueba un resumen PENDIENTE; el botón está deshabilitado en uno APROBADO', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ ...resumenPendiente, estado_revision: 'APROBADO' });
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Resúmenes');
    const filaPend = (await screen.findByText('2026-06-24')).closest('tr')!;
    expect(within(filaPend).getByRole('button', { name: 'Aprobar' })).toBeEnabled();

    const filaApr = screen.getByText('2026-06-23').closest('tr')!;
    expect(within(filaApr).getByRole('button', { name: 'Aprobar' })).toBeDisabled();

    fireEvent.click(within(filaPend).getByRole('button', { name: 'Aprobar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/control-asistencia/resumenes-asistencia-diario/s1/aprobar/',
        {},
      ),
    );
    confirmSpy.mockRestore();
  });

  it('filtra resúmenes por estado de revisión', async () => {
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Resúmenes');
    await screen.findByLabelText('Estado de revisión');
    fireEvent.mouseDown(screen.getByLabelText('Estado de revisión'));
    fireEvent.click(await screen.findByRole('option', { name: 'Aprobado' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        '/control-asistencia/resumenes-asistencia-diario/?estado_revision=APROBADO',
      ),
    );
  });

  it('elimina un resumen con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Resúmenes');
    const fila = (await screen.findByText('2026-06-24')).closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/control-asistencia/resumenes-asistencia-diario/s1/'),
    );
    confirmSpy.mockRestore();
  });

  it('muestra el error del backend al generar resúmenes', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ error: 'fecha inválida' })));
    renderPage();
    await screen.findByText('Diurno');
    irAPestana('Resúmenes');
    fireEvent.click(await screen.findByRole('button', { name: 'Generar resúmenes' }));
    expect(await screen.findByText(/fecha inválida/)).toBeInTheDocument();
  });
});
