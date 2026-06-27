import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  esquemasComisionService,
  esquemasComisionCategoriaService,
  comisionesService,
  type EsquemaComisionPayload,
  type EsquemaComisionCategoriaPayload,
} from '../services/comisionesService';

const esquemaPayload: EsquemaComisionPayload = {
  vendedor: 'u1',
  porcentaje_base: '5.0000',
  vigente_desde: '2026-01-01',
  vigente_hasta: null,
  activo: true,
};

const categoriaPayload: EsquemaComisionCategoriaPayload = {
  esquema: 'esq1',
  categoria: 'cat1',
  porcentaje: '8.0000',
};

describe('esquemasComisionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza la respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_esquema_comision: 'esq1' }] });
    const r = await esquemasComisionService.getAll();
    expect(get).toHaveBeenCalledWith('/ventas/esquemas-comision/');
    expect(r).toEqual([{ id_esquema_comision: 'esq1' }]);
  });

  it('getAll acepta la rama array', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_esquema_comision: 'esq1' }]);
    const r = await esquemasComisionService.getAll();
    expect(r).toHaveLength(1);
  });

  it('getAll normaliza una respuesta vacía/no reconocida', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    const r = await esquemasComisionService.getAll();
    expect(r).toEqual([]);
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_esquema_comision: 'esq2' });
    await esquemasComisionService.create(esquemaPayload);
    expect(post).toHaveBeenCalledWith('/ventas/esquemas-comision/', esquemaPayload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_esquema_comision: 'esq1' });
    await esquemasComisionService.update('esq1', esquemaPayload);
    expect(patch).toHaveBeenCalledWith('/ventas/esquemas-comision/esq1/', esquemaPayload);
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    await esquemasComisionService.remove('esq1');
    expect(del).toHaveBeenCalledWith('/ventas/esquemas-comision/esq1/');
  });
});

describe('esquemasComisionCategoriaService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll filtra por esquema en el querystring y en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_esquema_comision_categoria: 'c1', esquema: 'esq1' },
      { id_esquema_comision_categoria: 'c2', esquema: 'otro' },
    ]);
    const r = await esquemasComisionCategoriaService.getAll({ esquema: 'esq1' });
    expect(get).toHaveBeenCalledWith('/ventas/esquemas-comision-categorias/?esquema=esq1');
    expect(r.map((c) => c.id_esquema_comision_categoria)).toEqual(['c1']);
  });

  it('getAll sin esquema no filtra (rama paginada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [{ id_esquema_comision_categoria: 'c1', esquema: 'esq1' }],
    });
    const r = await esquemasComisionCategoriaService.getAll();
    expect(get).toHaveBeenCalledWith('/ventas/esquemas-comision-categorias/');
    expect(r).toHaveLength(1);
  });

  it('getAll normaliza una respuesta vacía', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    const r = await esquemasComisionCategoriaService.getAll({ esquema: 'esq1' });
    expect(r).toEqual([]);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_esquema_comision_categoria: 'c1' });
    await esquemasComisionCategoriaService.create(categoriaPayload);
    expect(post).toHaveBeenCalledWith(
      '/ventas/esquemas-comision-categorias/',
      categoriaPayload,
    );

    vi.mocked(patch).mockResolvedValue({ id_esquema_comision_categoria: 'c1' });
    await esquemasComisionCategoriaService.update('c1', categoriaPayload);
    expect(patch).toHaveBeenCalledWith(
      '/ventas/esquemas-comision-categorias/c1/',
      categoriaPayload,
    );

    vi.mocked(del).mockResolvedValue(undefined);
    await esquemasComisionCategoriaService.remove('c1');
    expect(del).toHaveBeenCalledWith('/ventas/esquemas-comision-categorias/c1/');
  });
});

describe('comisionesService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_comision_venta: 'k1' }] });
    const r = await comisionesService.getAll({
      vendedor: 'u1',
      estado: 'DEVENGADA',
      desde: '2026-01-01',
      hasta: '2026-06-30',
    });
    expect(get).toHaveBeenCalledWith(
      '/ventas/comisiones/?vendedor=u1&estado=DEVENGADA&desde=2026-01-01&hasta=2026-06-30',
    );
    expect(r).toEqual([{ id_comision_venta: 'k1' }]);
  });

  it('getAll sin parámetros pega al endpoint base (rama array)', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_comision_venta: 'k1' }]);
    const r = await comisionesService.getAll();
    expect(get).toHaveBeenCalledWith('/ventas/comisiones/');
    expect(r).toHaveLength(1);
  });

  it('getAll normaliza una respuesta vacía/no reconocida', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    const r = await comisionesService.getAll({ estado: '' });
    expect(get).toHaveBeenCalledWith('/ventas/comisiones/');
    expect(r).toEqual([]);
  });

  it('resumen arma el querystring con filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ resultados: [] });
    await comisionesService.resumen({ vendedor: 'u1', estado: 'LIQUIDADA' });
    expect(get).toHaveBeenCalledWith(
      '/ventas/comisiones/resumen/?vendedor=u1&estado=LIQUIDADA',
    );
  });

  it('resumen sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce({ resultados: [{ vendedor: 'u1' }] });
    const r = await comisionesService.resumen();
    expect(get).toHaveBeenCalledWith('/ventas/comisiones/resumen/');
    expect(r.resultados).toHaveLength(1);
  });

  it('liquidar postea vendedor + período', async () => {
    vi.mocked(post).mockResolvedValue({
      vendedor: 'u1',
      desde: '2026-01-01',
      hasta: '2026-06-30',
      liquidadas: 3,
      monto_total: '120.0000',
    });
    const r = await comisionesService.liquidar({
      vendedor: 'u1',
      desde: '2026-01-01',
      hasta: '2026-06-30',
    });
    expect(post).toHaveBeenCalledWith('/ventas/comisiones/liquidar/', {
      vendedor: 'u1',
      desde: '2026-01-01',
      hasta: '2026-06-30',
    });
    expect(r.liquidadas).toBe(3);
  });

  it('liquidar propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ error: 'desde > hasta' })));
    await expect(
      comisionesService.liquidar({ vendedor: 'u1', desde: '2026-06-30', hasta: '2026-01-01' }),
    ).rejects.toThrow();
  });
});
