import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

import { get, post } from '../services/api';
import {
  recepcionesService,
  entregasService,
  reportesInventarioService,
} from '../services/inventarioService';

describe('operaciones de inventario (servicio)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('list normaliza respuesta paginada del backend', async () => {
    vi.mocked(get).mockResolvedValue({ results: [{ id_operacion: 'op-1', numero: 'REC-1' }], count: 1 });
    const ops = await recepcionesService.list();
    expect(get).toHaveBeenCalledWith('/inventario/recepciones/');
    expect(ops).toHaveLength(1);
    expect(ops[0].numero).toBe('REC-1');
  });

  it('create postea al endpoint del tipo', async () => {
    vi.mocked(post).mockResolvedValue({ id_operacion: 'op-2', numero: 'ENT-1' });
    await entregasService.create({ almacen: 'a1', origen_tipo: 'TRANSFER', lineas: [] });
    expect(post).toHaveBeenCalledWith('/inventario/entregas/', expect.objectContaining({ almacen: 'a1' }));
  });

  it('confirmStep llama al endpoint step/{id}/confirm', async () => {
    vi.mocked(post).mockResolvedValue({ id_operacion: 'op-1' });
    await recepcionesService.confirmStep('op-1', 'step-9');
    expect(post).toHaveBeenCalledWith('/inventario/recepciones/op-1/step/step-9/confirm/', {});
  });

  it('reportesInventarioService.valoracion con filtro arma el querystring', async () => {
    vi.mocked(get).mockResolvedValue({
      valoracion: [{ producto: 'P', almacen: 'A', metodo: 'FIFO', cantidad: '5', valor_total: '100', costo_promedio: '20' }],
    });
    const filas = await reportesInventarioService.valoracion({ producto: 'p1' });
    expect(get).toHaveBeenCalledWith('/inventario/reportes/valoracion/?producto=p1');
    expect(filas[0].metodo).toBe('FIFO');
  });

  it('reportesInventarioService.valoracion sin filtros ni datos devuelve []', async () => {
    vi.mocked(get).mockResolvedValue({});
    const filas = await reportesInventarioService.valoracion();
    expect(get).toHaveBeenCalledWith('/inventario/reportes/valoracion/');
    expect(filas).toEqual([]);
  });
});
