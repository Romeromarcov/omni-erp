import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

import { get, post, patch } from '../services/api';
import {
  contabilidadService,
  type CrearCuentaPayload,
  type MapeoContablePayload,
} from '../services/contabilidadService';

const cuentaPayload: CrearCuentaPayload = {
  id_empresa: 'e1',
  codigo_cuenta: '6.1.01',
  nombre_cuenta: 'Servicios básicos',
  tipo_cuenta: 'GASTO',
  naturaleza: 'DEUDORA',
  id_cuenta_padre: null,
  nivel: 3,
};

const mapeoPayload: MapeoContablePayload = {
  id_empresa: 'e1',
  tipo_asiento: 'GASTO',
  cuenta_debe: 'cta-1',
  cuenta_haber: 'cta-2',
  descripcion_plantilla: 'Gasto contado',
  activo: true,
};

describe('contabilidadService — plan de cuentas', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getPlanCuentas normaliza array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_cuenta_contable: 'c1' }]);
    const r = await contabilidadService.getPlanCuentas();
    expect(get).toHaveBeenCalledWith('/contabilidad/plan-cuentas/?page_size=1000');
    expect(r).toEqual([{ id_cuenta_contable: 'c1' }]);
  });

  it('getPlanCuentas normaliza respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ count: 1, results: [{ id_cuenta_contable: 'c1' }] });
    expect((await contabilidadService.getPlanCuentas()).length).toBe(1);
  });

  it('getPlanCuentas ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await contabilidadService.getPlanCuentas()).toEqual([]);
  });

  it('crearCuenta postea el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_cuenta_contable: 'c2' });
    await contabilidadService.crearCuenta(cuentaPayload);
    expect(post).toHaveBeenCalledWith('/contabilidad/plan-cuentas/', cuentaPayload);
  });

  it('crearCuenta propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('código duplicado'));
    await expect(contabilidadService.crearCuenta(cuentaPayload)).rejects.toThrow('duplicado');
  });
});

describe('contabilidadService — asientos', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAsientosPaginated sin filtros usa solo page/page_size por defecto', async () => {
    vi.mocked(get).mockResolvedValueOnce({ count: 0, results: [] });
    await contabilidadService.getAsientosPaginated();
    expect(get).toHaveBeenCalledWith('/contabilidad/asientos-contables/?page=1&page_size=20');
  });

  it('getAsientosPaginated con page/pageSize explícitos', async () => {
    vi.mocked(get).mockResolvedValueOnce({ count: 0, results: [] });
    await contabilidadService.getAsientosPaginated(3, 50);
    expect(get).toHaveBeenCalledWith('/contabilidad/asientos-contables/?page=3&page_size=50');
  });

  it('getAsientosPaginated aplica TODOS los filtros (estado + rango de fechas)', async () => {
    vi.mocked(get).mockResolvedValueOnce({ count: 0, results: [] });
    await contabilidadService.getAsientosPaginated(1, 20, {
      estado: 'APROBADO',
      fechaDesde: '2026-01-01',
      fechaHasta: '2026-12-31',
    });
    expect(get).toHaveBeenCalledWith(
      '/contabilidad/asientos-contables/?page=1&page_size=20&estado_asiento=APROBADO&fecha_asiento__gte=2026-01-01&fecha_asiento__lte=2026-12-31',
    );
  });

  it('getAsientosPaginated solo con estado', async () => {
    vi.mocked(get).mockResolvedValueOnce({ count: 0, results: [] });
    await contabilidadService.getAsientosPaginated(1, 20, { estado: 'BORRADOR' });
    expect(get).toHaveBeenCalledWith(
      '/contabilidad/asientos-contables/?page=1&page_size=20&estado_asiento=BORRADOR',
    );
  });

  it('getAsientosPaginated solo con fechaDesde', async () => {
    vi.mocked(get).mockResolvedValueOnce({ count: 0, results: [] });
    await contabilidadService.getAsientosPaginated(1, 20, { fechaDesde: '2026-06-01' });
    expect(get).toHaveBeenCalledWith(
      '/contabilidad/asientos-contables/?page=1&page_size=20&fecha_asiento__gte=2026-06-01',
    );
  });

  it('getAsientosPaginated solo con fechaHasta', async () => {
    vi.mocked(get).mockResolvedValueOnce({ count: 0, results: [] });
    await contabilidadService.getAsientosPaginated(1, 20, { fechaHasta: '2026-06-30' });
    expect(get).toHaveBeenCalledWith(
      '/contabilidad/asientos-contables/?page=1&page_size=20&fecha_asiento__lte=2026-06-30',
    );
  });

  it('getAsientosPaginated devuelve la respuesta paginada tal cual (rama with results)', async () => {
    const paginada = { count: 1, next: null, previous: null, results: [{ id_asiento: 'a1' }] };
    vi.mocked(get).mockResolvedValueOnce(paginada);
    const r = await contabilidadService.getAsientosPaginated();
    expect(r).toBe(paginada);
  });

  it('getAsientosPaginated envuelve un array directo en estructura paginada (rama sin results)', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_asiento: 'a1' }, { id_asiento: 'a2' }]);
    const r = await contabilidadService.getAsientosPaginated();
    expect(r.count).toBe(2);
    expect(r.next).toBeNull();
    expect(r.results.map((a) => a.id_asiento)).toEqual(['a1', 'a2']);
  });

  it('getAsientosPaginated ante respuesta nula envuelve [] (paginada fallback)', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    const r = await contabilidadService.getAsientosPaginated();
    expect(r.count).toBe(0);
    expect(r.results).toEqual([]);
  });

  it('getAsiento pega al detalle por id', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_asiento: 'a1' });
    await contabilidadService.getAsiento('a1');
    expect(get).toHaveBeenCalledWith('/contabilidad/asientos-contables/a1/');
  });

  it('getDetallesAsiento normaliza array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_detalle_asiento: 'd1' }]);
    const r = await contabilidadService.getDetallesAsiento('a1');
    expect(get).toHaveBeenCalledWith('/contabilidad/detalles-asiento/?id_asiento=a1');
    expect(r.length).toBe(1);
  });

  it('getDetallesAsiento normaliza respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_detalle_asiento: 'd1' }] });
    expect((await contabilidadService.getDetallesAsiento('a1')).length).toBe(1);
  });
});

describe('contabilidadService — mapeos', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getMapeos normaliza array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_mapeo: 'm1' }]);
    const r = await contabilidadService.getMapeos();
    expect(get).toHaveBeenCalledWith('/contabilidad/mapeos-contables/');
    expect(r.length).toBe(1);
  });

  it('getMapeos normaliza respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_mapeo: 'm1' }] });
    expect((await contabilidadService.getMapeos()).length).toBe(1);
  });

  it('getTiposAsiento normaliza la lista', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ value: 'GASTO', label: 'Gasto' }]);
    const r = await contabilidadService.getTiposAsiento();
    expect(get).toHaveBeenCalledWith('/contabilidad/mapeos-contables/tipos-asiento/');
    expect(r[0].value).toBe('GASTO');
  });

  it('getTiposAsiento ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as never);
    expect(await contabilidadService.getTiposAsiento()).toEqual([]);
  });

  it('crearMapeo postea el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_mapeo: 'm1' });
    await contabilidadService.crearMapeo(mapeoPayload);
    expect(post).toHaveBeenCalledWith('/contabilidad/mapeos-contables/', mapeoPayload);
  });

  it('crearMapeo propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('mapeo duplicado'));
    await expect(contabilidadService.crearMapeo(mapeoPayload)).rejects.toThrow('duplicado');
  });

  it('actualizarMapeo parchea por id con payload parcial', async () => {
    vi.mocked(patch).mockResolvedValue({ id_mapeo: 'm1' });
    await contabilidadService.actualizarMapeo('m1', { activo: false });
    expect(patch).toHaveBeenCalledWith('/contabilidad/mapeos-contables/m1/', { activo: false });
  });
});
