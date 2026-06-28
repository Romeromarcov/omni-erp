import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

import { get, post } from '../services/api';
import { nominaService } from '../services/nominaService';
import type { ProcesoNomina, ReciboNomina } from '../services/nominaService';

const proceso: ProcesoNomina = {
  id_proceso_nomina: 'proc-1',
  id_empresa: 'emp-1',
  id_periodo_nomina: 'per-1',
  numero_proceso: 'NOM-2026-06',
  fecha_proceso: '2026-06-12T10:00:00Z',
  total_empleados: 2,
  total_devengado: '1500.0000',
  total_deducciones: '82.5000',
  total_neto: '1417.5000',
  estado: 'EN_PROCESO',
  observaciones: null,
  fecha_creacion: '2026-06-12T09:00:00Z',
};

const recibo: ReciboNomina = {
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
};

describe('nominaService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getProcesosPaginated pasa la página y devuelve la respuesta DRF', async () => {
    vi.mocked(get).mockResolvedValue({ count: 1, next: null, previous: null, results: [proceso] });
    const res = await nominaService.getProcesosPaginated(3);
    expect(get).toHaveBeenCalledWith('/nomina/procesos-nomina/?page=3');
    expect(res.results[0].numero_proceso).toBe('NOM-2026-06');
  });

  it('getProcesosPaginated normaliza listas directas', async () => {
    vi.mocked(get).mockResolvedValue([proceso]);
    const res = await nominaService.getProcesosPaginated();
    expect(res).toEqual({ count: 1, next: null, previous: null, results: [proceso] });
  });

  it('getProceso consulta el detalle por id', async () => {
    vi.mocked(get).mockResolvedValue(proceso);
    const res = await nominaService.getProceso('proc-1');
    expect(get).toHaveBeenCalledWith('/nomina/procesos-nomina/proc-1/');
    expect(res.estado).toBe('EN_PROCESO');
  });

  it('crearProceso postea el payload completo (la empresa va explícita)', async () => {
    vi.mocked(post).mockResolvedValue(proceso);
    await nominaService.crearProceso({
      id_empresa: 'emp-1',
      id_periodo_nomina: 'per-1',
      numero_proceso: 'NOM-2026-06',
      fecha_proceso: '2026-06-12T10:00:00.000Z',
    });
    expect(post).toHaveBeenCalledWith('/nomina/procesos-nomina/', {
      id_empresa: 'emp-1',
      id_periodo_nomina: 'per-1',
      numero_proceso: 'NOM-2026-06',
      fecha_proceso: '2026-06-12T10:00:00.000Z',
    });
  });

  it('procesarProceso postea el body {empleados} con horas como string (PR #80)', async () => {
    vi.mocked(post).mockResolvedValue({ ...proceso, estado: 'COMPLETADO', asiento_contable: 'as-1' });
    const res = await nominaService.procesarProceso('proc-1', {
      '1': { horas_extra_diurnas: '4', horas_nocturnas: '8' },
      '2': { horas_extra_nocturnas: '2.5' },
    });
    expect(post).toHaveBeenCalledWith('/nomina/procesos-nomina/proc-1/procesar/', {
      empleados: {
        '1': { horas_extra_diurnas: '4', horas_nocturnas: '8' },
        '2': { horas_extra_nocturnas: '2.5' },
      },
    });
    expect(res.asiento_contable).toBe('as-1');
  });

  it('procesarProceso con mapa vacío procesa con defaults del motor', async () => {
    vi.mocked(post).mockResolvedValue({ ...proceso, estado: 'COMPLETADO', asiento_contable: null });
    await nominaService.procesarProceso('proc-1', {});
    expect(post).toHaveBeenCalledWith('/nomina/procesos-nomina/proc-1/procesar/', {
      empleados: {},
    });
  });

  it('getRecibosProceso usa el filtro real del ViewSet y camina las páginas', async () => {
    vi.mocked(get)
      .mockResolvedValueOnce({ count: 2, next: 'pag2', previous: null, results: [recibo] })
      .mockResolvedValueOnce({
        count: 2,
        next: null,
        previous: null,
        results: [{ ...recibo, id_nomina: 'nom-2', id_empleado: 2 }],
      });
    const res = await nominaService.getRecibosProceso('proc-1');
    expect(get).toHaveBeenNthCalledWith(1, '/nomina/nominas/?id_proceso_nomina=proc-1&page=1');
    expect(get).toHaveBeenNthCalledWith(2, '/nomina/nominas/?id_proceso_nomina=proc-1&page=2');
    expect(res.map((r) => r.id_nomina)).toEqual(['nom-1', 'nom-2']);
  });

  it('aprobarProceso postea a la acción aprobar del proceso', async () => {
    vi.mocked(post).mockResolvedValue({ ...proceso, estado: 'APROBADO' });
    const res = await nominaService.aprobarProceso('proc-1');
    expect(post).toHaveBeenCalledWith('/nomina/procesos-nomina/proc-1/aprobar/', {});
    expect(res.estado).toBe('APROBADO');
  });

  it('aprobarRecibo postea a la acción aprobar del recibo', async () => {
    vi.mocked(post).mockResolvedValue({ ...recibo, estado: 'APROBADA' });
    const res = await nominaService.aprobarRecibo('nom-1');
    expect(post).toHaveBeenCalledWith('/nomina/nominas/nom-1/aprobar/', {});
    expect(res.estado).toBe('APROBADA');
  });

  it('marcarReciboPagada postea a la acción marcar_pagada del recibo', async () => {
    vi.mocked(post).mockResolvedValue({ ...recibo, estado: 'PAGADA' });
    const res = await nominaService.marcarReciboPagada('nom-1');
    expect(post).toHaveBeenCalledWith('/nomina/nominas/nom-1/marcar_pagada/', {});
    expect(res.estado).toBe('PAGADA');
  });

  it('getPeriodos camina las páginas hasta agotar next', async () => {
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
    vi.mocked(get).mockResolvedValue({ count: 1, next: null, previous: null, results: [periodo] });
    const res = await nominaService.getPeriodos();
    expect(get).toHaveBeenCalledWith('/nomina/periodos-nomina/?page=1');
    expect(res).toHaveLength(1);
  });

  it('crearPeriodo postea el payload del período', async () => {
    vi.mocked(post).mockResolvedValue({ id_periodo_nomina: 'per-2' });
    await nominaService.crearPeriodo({
      id_empresa: 'emp-1',
      nombre_periodo: 'Julio 2026',
      fecha_inicio: '2026-07-01',
      fecha_fin: '2026-07-31',
      fecha_pago: '2026-07-31',
      tipo_periodo: 'MENSUAL',
    });
    expect(post).toHaveBeenCalledWith('/nomina/periodos-nomina/', {
      id_empresa: 'emp-1',
      nombre_periodo: 'Julio 2026',
      fecha_inicio: '2026-07-01',
      fecha_fin: '2026-07-31',
      fecha_pago: '2026-07-31',
      tipo_periodo: 'MENSUAL',
    });
  });
});
