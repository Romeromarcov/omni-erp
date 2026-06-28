import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  conceptosNominaService,
  procesosNominaExtrasalarialService,
  nominasExtrasalarialService,
  type ConceptoNominaPayload,
  type ProcesoNominaExtrasalarialPayload,
} from '../services/nominaExtrasService';

const conceptoPayload: ConceptoNominaPayload = {
  id_empresa: 'e1',
  codigo_concepto: 'DEV-001',
  nombre_concepto: 'Bono de productividad',
  tipo_concepto: 'DEVENGADO',
  categoria: 'BONO',
  formula_calculo: null,
  es_fijo: true,
  monto_fijo: '150.0000',
  es_porcentaje: false,
  porcentaje: null,
  activo: true,
};

const procesoPayload: ProcesoNominaExtrasalarialPayload = {
  id_empresa: 'e1',
  numero_proceso: 'EXTRA-001',
  tipo_proceso: 'AGUINALDO',
  fecha_proceso: '2026-06-27T00:00:00.000Z',
  fecha_corte: '2026-06-27',
  observaciones: null,
};

describe('conceptosNominaService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza la rama paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_concepto_nomina: 'c1' }] });
    const r = await conceptosNominaService.getAll();
    expect(get).toHaveBeenCalledWith('/nomina/conceptos-nomina/');
    expect(r).toEqual([{ id_concepto_nomina: 'c1' }]);
  });

  it('getAll normaliza la rama array', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_concepto_nomina: 'c1' }]);
    expect(await conceptosNominaService.getAll()).toEqual([{ id_concepto_nomina: 'c1' }]);
  });

  it('getAll normaliza respuesta vacía/no reconocida', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    expect(await conceptosNominaService.getAll()).toEqual([]);
  });

  it('porTipo arma el querystring con el tipo codificado', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_concepto_nomina: 'c1' }]);
    await conceptosNominaService.porTipo('DEDUCCION');
    expect(get).toHaveBeenCalledWith('/nomina/conceptos-nomina/por_tipo/?tipo=DEDUCCION');
  });

  it('devengados / deducciones pegan a sus acciones', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_concepto_nomina: 'c1' }] });
    await conceptosNominaService.devengados();
    expect(get).toHaveBeenCalledWith('/nomina/conceptos-nomina/devengados/');

    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    expect(await conceptosNominaService.deducciones()).toEqual([]);
    expect(get).toHaveBeenCalledWith('/nomina/conceptos-nomina/deducciones/');
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_concepto_nomina: 'c1' });
    await conceptosNominaService.getById('c1');
    expect(get).toHaveBeenCalledWith('/nomina/conceptos-nomina/c1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_concepto_nomina: 'c2' });
    await conceptosNominaService.create(conceptoPayload);
    expect(post).toHaveBeenCalledWith('/nomina/conceptos-nomina/', conceptoPayload);

    vi.mocked(patch).mockResolvedValue({ id_concepto_nomina: 'c1' });
    await conceptosNominaService.update('c1', conceptoPayload);
    expect(patch).toHaveBeenCalledWith('/nomina/conceptos-nomina/c1/', conceptoPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await conceptosNominaService.remove('c1');
    expect(del).toHaveBeenCalledWith('/nomina/conceptos-nomina/c1/');
  });
});

describe('procesosNominaExtrasalarialService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza array y getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_proceso_extrasalarial: 'p1' }]);
    expect(await procesosNominaExtrasalarialService.getAll()).toEqual([
      { id_proceso_extrasalarial: 'p1' },
    ]);
    expect(get).toHaveBeenCalledWith('/nomina/procesos-nomina-extrasalarial/');

    vi.mocked(get).mockResolvedValueOnce({ id_proceso_extrasalarial: 'p1' });
    await procesosNominaExtrasalarialService.getById('p1');
    expect(get).toHaveBeenCalledWith('/nomina/procesos-nomina-extrasalarial/p1/');
  });

  it('getAll normaliza respuesta vacía', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    expect(await procesosNominaExtrasalarialService.getAll()).toEqual([]);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_proceso_extrasalarial: 'p2' });
    await procesosNominaExtrasalarialService.create(procesoPayload);
    expect(post).toHaveBeenCalledWith('/nomina/procesos-nomina-extrasalarial/', procesoPayload);

    vi.mocked(patch).mockResolvedValue({ id_proceso_extrasalarial: 'p1' });
    await procesosNominaExtrasalarialService.update('p1', procesoPayload);
    expect(patch).toHaveBeenCalledWith('/nomina/procesos-nomina-extrasalarial/p1/', procesoPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await procesosNominaExtrasalarialService.remove('p1');
    expect(del).toHaveBeenCalledWith('/nomina/procesos-nomina-extrasalarial/p1/');
  });

  it('procesar / aprobar pegan a sus acciones con body vacío', async () => {
    vi.mocked(post).mockResolvedValue({ id_proceso_extrasalarial: 'p1', estado: 'COMPLETADO' });
    await procesosNominaExtrasalarialService.procesar('p1');
    expect(post).toHaveBeenCalledWith('/nomina/procesos-nomina-extrasalarial/p1/procesar/', {});

    vi.mocked(post).mockResolvedValue({ id_proceso_extrasalarial: 'p1', estado: 'APROBADO' });
    await procesosNominaExtrasalarialService.aprobar('p1');
    expect(post).toHaveBeenCalledWith('/nomina/procesos-nomina-extrasalarial/p1/aprobar/', {});
  });
});

describe('nominasExtrasalarialService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll sin filtro pega a la lista (rama paginada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_nomina_extrasalarial: 'r1' }] });
    const r = await nominasExtrasalarialService.getAll();
    expect(get).toHaveBeenCalledWith('/nomina/nominas-extrasalarial/');
    expect(r).toEqual([{ id_nomina_extrasalarial: 'r1' }]);
  });

  it('getAll filtra por proceso vía querystring', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_nomina_extrasalarial: 'r1' }]);
    await nominasExtrasalarialService.getAll({ proceso: 'p1' });
    expect(get).toHaveBeenCalledWith(
      '/nomina/nominas-extrasalarial/?id_proceso_extrasalarial=p1',
    );
  });

  it('getAll normaliza respuesta vacía', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    expect(await nominasExtrasalarialService.getAll({ proceso: 'p1' })).toEqual([]);
  });

  it('aprobar / marcarPagada pegan a sus acciones con body vacío', async () => {
    vi.mocked(post).mockResolvedValue({ id_nomina_extrasalarial: 'r1', estado: 'APROBADA' });
    await nominasExtrasalarialService.aprobar('r1');
    expect(post).toHaveBeenCalledWith('/nomina/nominas-extrasalarial/r1/aprobar/', {});

    vi.mocked(post).mockResolvedValue({ id_nomina_extrasalarial: 'r1', estado: 'PAGADA' });
    await nominasExtrasalarialService.marcarPagada('r1');
    expect(post).toHaveBeenCalledWith('/nomina/nominas-extrasalarial/r1/marcar_pagada/', {});
  });
});
