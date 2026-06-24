import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  costosProduccionService,
  costosEstandarProductoService,
  analisisVariacionService,
  type CostoProduccionPayload,
  type CostoEstandarProductoPayload,
  type AnalisisVariacionCostoPayload,
} from '../services/costosService';

const produccionPayload: CostoProduccionPayload = {
  id_empresa: 'e1',
  id_orden_produccion: 'op1',
  tipo_costo: 'MATERIAL_DIRECTO',
  costo_unitario: '10.0000',
  cantidad: '5.0000',
  costo_total: '50.0000',
  id_moneda: 'm1',
  fecha_calculo: '2026-06-24',
  observaciones: 'nota',
  activo: true,
};

const estandarPayload: CostoEstandarProductoPayload = {
  id_empresa: 'e1',
  id_producto: 'p1',
  tipo_costo: 'MANO_OBRA_DIRECTA',
  costo_unitario_estandar: '12.0000',
  id_moneda: 'm1',
  fecha_vigencia_desde: '2026-06-01',
  fecha_vigencia_hasta: null,
  activo: true,
};

const variacionPayload: AnalisisVariacionCostoPayload = {
  id_empresa: 'e1',
  id_orden_produccion: 'op1',
  id_producto: 'p1',
  tipo_costo: 'OVERHEAD',
  costo_estandar: '50.0000',
  costo_real: '48.0000',
  variacion_cantidad: '0.0000',
  variacion_precio: '2.0000',
  variacion_total: '2.0000',
  porcentaje_variacion: '4.00',
  tipo_variacion: 'FAVORABLE',
  fecha_analisis: '2026-06-24',
  observaciones: null,
  activo: true,
};

describe('costosProduccionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con empresa y orden', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_costo_produccion: 'c1' }] });
    const r = await costosProduccionService.getAll({ empresa: 'e1', orden: 'op1' });
    expect(get).toHaveBeenCalledWith(
      '/costos/costos-produccion/?empresa=e1&id_orden_produccion=op1',
    );
    expect(r).toEqual([{ id_costo_produccion: 'c1' }]);
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_costo_produccion: 'c1' }]);
    await costosProduccionService.getAll();
    expect(get).toHaveBeenCalledWith('/costos/costos-produccion/');
  });

  it('getAll con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await costosProduccionService.getAll({});
    expect(get).toHaveBeenCalledWith('/costos/costos-produccion/');
  });

  it('getAll solo con empresa', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await costosProduccionService.getAll({ empresa: 'e1' });
    expect(get).toHaveBeenCalledWith('/costos/costos-produccion/?empresa=e1');
  });

  it('getAll solo con orden', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await costosProduccionService.getAll({ orden: 'op1' });
    expect(get).toHaveBeenCalledWith('/costos/costos-produccion/?id_orden_produccion=op1');
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await costosProduccionService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_costo_produccion: 'c1' });
    await costosProduccionService.getById('c1');
    expect(get).toHaveBeenCalledWith('/costos/costos-produccion/c1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_costo_produccion: 'c1' });
    await costosProduccionService.create(produccionPayload);
    expect(post).toHaveBeenCalledWith('/costos/costos-produccion/', produccionPayload);

    vi.mocked(patch).mockResolvedValue({ id_costo_produccion: 'c1' });
    await costosProduccionService.update('c1', produccionPayload);
    expect(patch).toHaveBeenCalledWith('/costos/costos-produccion/c1/', produccionPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await costosProduccionService.remove('c1');
    expect(del).toHaveBeenCalledWith('/costos/costos-produccion/c1/');
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('boom'));
    await expect(costosProduccionService.create(produccionPayload)).rejects.toThrow('boom');
  });
});

describe('costosEstandarProductoService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con empresa y producto', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_costo_estandar: 'c1' }] });
    const r = await costosEstandarProductoService.getAll({ empresa: 'e1', producto: 'p1' });
    expect(get).toHaveBeenCalledWith(
      '/costos/costos-estandar-producto/?empresa=e1&id_producto=p1',
    );
    expect(r).toEqual([{ id_costo_estandar: 'c1' }]);
  });

  it('getAll sin parámetros', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await costosEstandarProductoService.getAll();
    expect(get).toHaveBeenCalledWith('/costos/costos-estandar-producto/');
  });

  it('getAll con objeto vacío', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await costosEstandarProductoService.getAll({});
    expect(get).toHaveBeenCalledWith('/costos/costos-estandar-producto/');
  });

  it('getAll solo con empresa', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await costosEstandarProductoService.getAll({ empresa: 'e1' });
    expect(get).toHaveBeenCalledWith('/costos/costos-estandar-producto/?empresa=e1');
  });

  it('getAll solo con producto', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await costosEstandarProductoService.getAll({ producto: 'p1' });
    expect(get).toHaveBeenCalledWith('/costos/costos-estandar-producto/?id_producto=p1');
  });

  it('getAll normaliza array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_costo_estandar: 'c1' }]);
    expect((await costosEstandarProductoService.getAll()).length).toBe(1);
  });

  it('getById', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_costo_estandar: 'c1' });
    await costosEstandarProductoService.getById('c1');
    expect(get).toHaveBeenCalledWith('/costos/costos-estandar-producto/c1/');
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_costo_estandar: 'c1' });
    await costosEstandarProductoService.create(estandarPayload);
    expect(post).toHaveBeenCalledWith('/costos/costos-estandar-producto/', estandarPayload);

    vi.mocked(patch).mockResolvedValue({ id_costo_estandar: 'c1' });
    await costosEstandarProductoService.update('c1', estandarPayload);
    expect(patch).toHaveBeenCalledWith('/costos/costos-estandar-producto/c1/', estandarPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await costosEstandarProductoService.remove('c1');
    expect(del).toHaveBeenCalledWith('/costos/costos-estandar-producto/c1/');
  });

  it('update propaga el error del backend', async () => {
    vi.mocked(patch).mockRejectedValueOnce(new Error('conflicto'));
    await expect(costosEstandarProductoService.update('c1', estandarPayload)).rejects.toThrow(
      'conflicto',
    );
  });
});

describe('analisisVariacionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con empresa, producto y orden', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_analisis_variacion: 'a1' }] });
    const r = await analisisVariacionService.getAll({
      empresa: 'e1',
      producto: 'p1',
      orden: 'op1',
    });
    expect(get).toHaveBeenCalledWith(
      '/costos/analisis-variacion-costo/?empresa=e1&id_producto=p1&id_orden_produccion=op1',
    );
    expect(r).toEqual([{ id_analisis_variacion: 'a1' }]);
  });

  it('getAll sin parámetros', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await analisisVariacionService.getAll();
    expect(get).toHaveBeenCalledWith('/costos/analisis-variacion-costo/');
  });

  it('getAll con objeto vacío', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await analisisVariacionService.getAll({});
    expect(get).toHaveBeenCalledWith('/costos/analisis-variacion-costo/');
  });

  it('getAll solo con empresa', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await analisisVariacionService.getAll({ empresa: 'e1' });
    expect(get).toHaveBeenCalledWith('/costos/analisis-variacion-costo/?empresa=e1');
  });

  it('getAll solo con producto', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await analisisVariacionService.getAll({ producto: 'p1' });
    expect(get).toHaveBeenCalledWith('/costos/analisis-variacion-costo/?id_producto=p1');
  });

  it('getAll solo con orden', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await analisisVariacionService.getAll({ orden: 'op1' });
    expect(get).toHaveBeenCalledWith('/costos/analisis-variacion-costo/?id_orden_produccion=op1');
  });

  it('getAll normaliza array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_analisis_variacion: 'a1' }]);
    expect((await analisisVariacionService.getAll()).length).toBe(1);
  });

  it('getById', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_analisis_variacion: 'a1' });
    await analisisVariacionService.getById('a1');
    expect(get).toHaveBeenCalledWith('/costos/analisis-variacion-costo/a1/');
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_analisis_variacion: 'a1' });
    await analisisVariacionService.create(variacionPayload);
    expect(post).toHaveBeenCalledWith('/costos/analisis-variacion-costo/', variacionPayload);

    vi.mocked(patch).mockResolvedValue({ id_analisis_variacion: 'a1' });
    await analisisVariacionService.update('a1', variacionPayload);
    expect(patch).toHaveBeenCalledWith('/costos/analisis-variacion-costo/a1/', variacionPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await analisisVariacionService.remove('a1');
    expect(del).toHaveBeenCalledWith('/costos/analisis-variacion-costo/a1/');
  });

  it('remove propaga el error del backend', async () => {
    vi.mocked(del).mockRejectedValueOnce(new Error('no encontrado'));
    await expect(analisisVariacionService.remove('a1')).rejects.toThrow('no encontrado');
  });
});
