import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  horariosTrabajoService,
  asignacionesHorarioService,
  registrosAsistenciaService,
  resumenesAsistenciaService,
  type HorarioTrabajoPayload,
  type AsignacionHorarioPayload,
  type RegistroAsistenciaPayload,
} from '../services/controlAsistenciaService';

const horarioPayload: HorarioTrabajoPayload = {
  id_empresa: 'e1',
  nombre_horario: 'Diurno',
  descripcion: 'Lun-Vie',
  dias_semana_json: null,
  total_horas_semanales: '40.00',
};

const asignacionPayload: AsignacionHorarioPayload = {
  id_empleado: 7,
  id_horario: 'h1',
  fecha_inicio: '2026-06-01',
  fecha_fin: null,
};

const registroPayload: RegistroAsistenciaPayload = {
  id_empleado: 7,
  fecha_hora_marcado: '2026-06-24T08:00:00Z',
  tipo_marcado: 'ENTRADA',
  metodo_marcado: 'WEB',
  observaciones: null,
};

beforeEach(() => vi.clearAllMocks());

// ── horariosTrabajoService ────────────────────────────────────────────────────

describe('horariosTrabajoService', () => {
  it('getAll arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_horario: 'h1' }] });
    const r = await horariosTrabajoService.getAll({ empresa: 'e1', activo: true, search: 'diu' });
    expect(get).toHaveBeenCalledWith(
      '/control-asistencia/horarios-trabajo/?id_empresa=e1&activo=true&search=diu',
    );
    expect(r).toEqual([{ id_horario: 'h1' }]);
  });

  it('getAll con activo=false incluye el flag (no se trata como ausente)', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await horariosTrabajoService.getAll({ activo: false });
    expect(get).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/?activo=false');
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await horariosTrabajoService.getAll();
    expect(get).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/');
  });

  it('getAll con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await horariosTrabajoService.getAll({});
    expect(get).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/');
  });

  it('getAll normaliza un array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_horario: 'h1' }, { id_horario: 'h2' }]);
    expect((await horariosTrabajoService.getAll()).length).toBe(2);
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await horariosTrabajoService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_horario: 'h1' });
    await horariosTrabajoService.getById('h1');
    expect(get).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/h1/');
  });

  it('activos pega a la acción activos/ y normaliza paginado', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_horario: 'h1' }] });
    const r = await horariosTrabajoService.activos();
    expect(get).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/activos/');
    expect(r.length).toBe(1);
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_horario: 'h1' });
    await horariosTrabajoService.create(horarioPayload);
    expect(post).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/', horarioPayload);
  });

  it('update parchea el payload', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id_horario: 'h1' });
    await horariosTrabajoService.update('h1', horarioPayload);
    expect(patch).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/h1/', horarioPayload);
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await horariosTrabajoService.remove('h1');
    expect(del).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/h1/');
  });

  it('desactivar postea cuerpo vacío', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_horario: 'h1', activo: false });
    await horariosTrabajoService.desactivar('h1');
    expect(post).toHaveBeenCalledWith('/control-asistencia/horarios-trabajo/h1/desactivar/', {});
  });

  it('desactivar propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('asignaciones activas'));
    await expect(horariosTrabajoService.desactivar('h1')).rejects.toThrow('asignaciones');
  });
});

// ── asignacionesHorarioService ────────────────────────────────────────────────

describe('asignacionesHorarioService', () => {
  it('getAll arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await asignacionesHorarioService.getAll({ empleado: 7, horario: 'h1', activo: true });
    expect(get).toHaveBeenCalledWith(
      '/control-asistencia/asignaciones-horario/?id_empleado=7&id_horario=h1&activo=true',
    );
  });

  it('getAll con empleado="" no agrega el filtro (rama vacía)', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await asignacionesHorarioService.getAll({ empleado: '' });
    expect(get).toHaveBeenCalledWith('/control-asistencia/asignaciones-horario/');
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await asignacionesHorarioService.getAll();
    expect(get).toHaveBeenCalledWith('/control-asistencia/asignaciones-horario/');
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_asignacion_horario: 'a1' });
    await asignacionesHorarioService.getById('a1');
    expect(get).toHaveBeenCalledWith('/control-asistencia/asignaciones-horario/a1/');
  });

  it('activas con empleado incluye el param empleado_id', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await asignacionesHorarioService.activas(7);
    expect(get).toHaveBeenCalledWith(
      '/control-asistencia/asignaciones-horario/activas/?empleado_id=7',
    );
  });

  it('activas sin empleado pega a la acción sin param', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await asignacionesHorarioService.activas();
    expect(get).toHaveBeenCalledWith('/control-asistencia/asignaciones-horario/activas/');
  });

  it('activas con empleado="" omite el param (rama vacía)', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await asignacionesHorarioService.activas('');
    expect(get).toHaveBeenCalledWith('/control-asistencia/asignaciones-horario/activas/');
  });

  it('porEmpleado pega a la acción con empleado_id codificado', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_asignacion_horario: 'a1' }] });
    const r = await asignacionesHorarioService.porEmpleado(7);
    expect(get).toHaveBeenCalledWith(
      '/control-asistencia/asignaciones-horario/por_empleado/?empleado_id=7',
    );
    expect(r.length).toBe(1);
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_asignacion_horario: 'a1' });
    await asignacionesHorarioService.create(asignacionPayload);
    expect(post).toHaveBeenCalledWith(
      '/control-asistencia/asignaciones-horario/',
      asignacionPayload,
    );
  });

  it('update parchea el payload', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id_asignacion_horario: 'a1' });
    await asignacionesHorarioService.update('a1', asignacionPayload);
    expect(patch).toHaveBeenCalledWith(
      '/control-asistencia/asignaciones-horario/a1/',
      asignacionPayload,
    );
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await asignacionesHorarioService.remove('a1');
    expect(del).toHaveBeenCalledWith('/control-asistencia/asignaciones-horario/a1/');
  });

  it('finalizar sin fecha manda cuerpo vacío', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_asignacion_horario: 'a1', activo: false });
    await asignacionesHorarioService.finalizar('a1');
    expect(post).toHaveBeenCalledWith('/control-asistencia/asignaciones-horario/a1/finalizar/', {});
  });

  it('finalizar con fecha la incluye', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_asignacion_horario: 'a1' });
    await asignacionesHorarioService.finalizar('a1', '2026-06-30');
    expect(post).toHaveBeenCalledWith('/control-asistencia/asignaciones-horario/a1/finalizar/', {
      fecha_fin: '2026-06-30',
    });
  });

  it('finalizar con fecha null manda cuerpo vacío (rama falsy)', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_asignacion_horario: 'a1' });
    await asignacionesHorarioService.finalizar('a1', null);
    expect(post).toHaveBeenCalledWith('/control-asistencia/asignaciones-horario/a1/finalizar/', {});
  });
});

// ── registrosAsistenciaService ────────────────────────────────────────────────

describe('registrosAsistenciaService', () => {
  it('getAll arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await registrosAsistenciaService.getAll({ empleado: 7, tipo: 'ENTRADA', metodo: 'WEB' });
    expect(get).toHaveBeenCalledWith(
      '/control-asistencia/registros-asistencia/?id_empleado=7&tipo_marcado=ENTRADA&metodo_marcado=WEB',
    );
  });

  it('getAll con empleado="" omite el filtro', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await registrosAsistenciaService.getAll({ empleado: '' });
    expect(get).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/');
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await registrosAsistenciaService.getAll();
    expect(get).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/');
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_registro_asistencia: 'r1' });
    await registrosAsistenciaService.getById('r1');
    expect(get).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/r1/');
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_registro_asistencia: 'r1' });
    await registrosAsistenciaService.create(registroPayload);
    expect(post).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/', registroPayload);
  });

  it('update parchea el payload', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id_registro_asistencia: 'r1' });
    await registrosAsistenciaService.update('r1', registroPayload);
    expect(patch).toHaveBeenCalledWith(
      '/control-asistencia/registros-asistencia/r1/',
      registroPayload,
    );
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await registrosAsistenciaService.remove('r1');
    expect(del).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/r1/');
  });

  it('marcarAsistencia con todos los campos los incluye', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_registro_asistencia: 'r1' });
    await registrosAsistenciaService.marcarAsistencia({
      empleado_id: 7,
      tipo_marcado: 'ENTRADA',
      metodo_marcado: 'GPS',
      observaciones: 'tarde',
    });
    expect(post).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/marcar_asistencia/', {
      empleado_id: 7,
      tipo_marcado: 'ENTRADA',
      metodo_marcado: 'GPS',
      observaciones: 'tarde',
    });
  });

  it('marcarAsistencia sin método ni observaciones manda solo lo requerido (ramas falsy)', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_registro_asistencia: 'r1' });
    await registrosAsistenciaService.marcarAsistencia({ empleado_id: 7, tipo_marcado: 'SALIDA' });
    expect(post).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/marcar_asistencia/', {
      empleado_id: 7,
      tipo_marcado: 'SALIDA',
    });
  });

  it('marcarAsistencia propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('Empleado no encontrado.'));
    await expect(
      registrosAsistenciaService.marcarAsistencia({ empleado_id: 9, tipo_marcado: 'ENTRADA' }),
    ).rejects.toThrow('Empleado');
  });

  it('porEmpleadoFecha con rango incluye fecha_inicio y fecha_fin', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_registro_asistencia: 'r1' }] });
    const r = await registrosAsistenciaService.porEmpleadoFecha({
      empleado: 7,
      fechaInicio: '2026-06-01',
      fechaFin: '2026-06-30',
    });
    expect(get).toHaveBeenCalledWith(
      '/control-asistencia/registros-asistencia/por_empleado_fecha/?empleado_id=7&fecha_inicio=2026-06-01&fecha_fin=2026-06-30',
    );
    expect(r.length).toBe(1);
  });

  it('porEmpleadoFecha sin rango solo manda empleado_id', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await registrosAsistenciaService.porEmpleadoFecha({ empleado: 7 });
    expect(get).toHaveBeenCalledWith(
      '/control-asistencia/registros-asistencia/por_empleado_fecha/?empleado_id=7',
    );
  });

  it('hoy con empleado incluye el param', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await registrosAsistenciaService.hoy(7);
    expect(get).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/hoy/?empleado_id=7');
  });

  it('hoy sin empleado pega a la acción sin param', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await registrosAsistenciaService.hoy();
    expect(get).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/hoy/');
  });

  it('hoy con empleado="" omite el param (rama vacía)', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await registrosAsistenciaService.hoy('');
    expect(get).toHaveBeenCalledWith('/control-asistencia/registros-asistencia/hoy/');
  });
});

// ── resumenesAsistenciaService ────────────────────────────────────────────────

describe('resumenesAsistenciaService', () => {
  it('getAll arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await resumenesAsistenciaService.getAll({
      empleado: 7,
      fecha: '2026-06-24',
      estado: 'PENDIENTE',
      ausencia: false,
    });
    expect(get).toHaveBeenCalledWith(
      '/control-asistencia/resumenes-asistencia-diario/?id_empleado=7&fecha=2026-06-24&estado_revision=PENDIENTE&es_ausencia=false',
    );
  });

  it('getAll con empleado="" omite el filtro de empleado', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await resumenesAsistenciaService.getAll({ empleado: '' });
    expect(get).toHaveBeenCalledWith('/control-asistencia/resumenes-asistencia-diario/');
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await resumenesAsistenciaService.getAll();
    expect(get).toHaveBeenCalledWith('/control-asistencia/resumenes-asistencia-diario/');
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_resumen_diario: 's1' });
    await resumenesAsistenciaService.getById('s1');
    expect(get).toHaveBeenCalledWith('/control-asistencia/resumenes-asistencia-diario/s1/');
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await resumenesAsistenciaService.remove('s1');
    expect(del).toHaveBeenCalledWith('/control-asistencia/resumenes-asistencia-diario/s1/');
  });

  it('generarResumenDiario con fecha y empleado los incluye', async () => {
    vi.mocked(post).mockResolvedValueOnce({ mensaje: 'ok', fecha: '2026-06-24' });
    await resumenesAsistenciaService.generarResumenDiario({
      fecha: '2026-06-24',
      empleadoId: 7,
    });
    expect(post).toHaveBeenCalledWith(
      '/control-asistencia/resumenes-asistencia-diario/generar_resumen_diario/',
      { fecha: '2026-06-24', empleado_id: 7 },
    );
  });

  it('generarResumenDiario sin parámetros manda cuerpo vacío', async () => {
    vi.mocked(post).mockResolvedValueOnce({ mensaje: 'ok', fecha: 'hoy' });
    await resumenesAsistenciaService.generarResumenDiario();
    expect(post).toHaveBeenCalledWith(
      '/control-asistencia/resumenes-asistencia-diario/generar_resumen_diario/',
      {},
    );
  });

  it('generarResumenDiario con empleadoId="" omite el campo (rama vacía)', async () => {
    vi.mocked(post).mockResolvedValueOnce({ mensaje: 'ok', fecha: '2026-06-24' });
    await resumenesAsistenciaService.generarResumenDiario({ fecha: '2026-06-24', empleadoId: '' });
    expect(post).toHaveBeenCalledWith(
      '/control-asistencia/resumenes-asistencia-diario/generar_resumen_diario/',
      { fecha: '2026-06-24' },
    );
  });

  it('aprobar sin observaciones manda cuerpo vacío', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_resumen_diario: 's1', estado_revision: 'APROBADO' });
    await resumenesAsistenciaService.aprobar('s1');
    expect(post).toHaveBeenCalledWith(
      '/control-asistencia/resumenes-asistencia-diario/s1/aprobar/',
      {},
    );
  });

  it('aprobar con observaciones las incluye', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_resumen_diario: 's1' });
    await resumenesAsistenciaService.aprobar('s1', 'visto bueno');
    expect(post).toHaveBeenCalledWith(
      '/control-asistencia/resumenes-asistencia-diario/s1/aprobar/',
      { observaciones: 'visto bueno' },
    );
  });

  it('aprobar propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('ya está aprobado'));
    await expect(resumenesAsistenciaService.aprobar('s1')).rejects.toThrow('aprobado');
  });

  it('pendientesRevision arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_resumen_diario: 's1' }] });
    const r = await resumenesAsistenciaService.pendientesRevision({
      empleado: 7,
      fechaDesde: '2026-06-01',
      fechaHasta: '2026-06-30',
    });
    expect(get).toHaveBeenCalledWith(
      '/control-asistencia/resumenes-asistencia-diario/pendientes_revision/?empleado_id=7&fecha_desde=2026-06-01&fecha_hasta=2026-06-30',
    );
    expect(r.length).toBe(1);
  });

  it('pendientesRevision sin parámetros pega a la acción base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await resumenesAsistenciaService.pendientesRevision();
    expect(get).toHaveBeenCalledWith(
      '/control-asistencia/resumenes-asistencia-diario/pendientes_revision/',
    );
  });

  it('pendientesRevision con empleado="" omite el filtro de empleado', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await resumenesAsistenciaService.pendientesRevision({ empleado: '' });
    expect(get).toHaveBeenCalledWith(
      '/control-asistencia/resumenes-asistencia-diario/pendientes_revision/',
    );
  });
});
