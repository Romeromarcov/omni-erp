import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  ubicacionesAlmacenService,
  movimientosInternosFondoService,
  fetchCajasEmpresa,
  pagosTercerosService,
  pagosParafiscalesService,
  type UbicacionAlmacenPayload,
  type MovimientoInternoFondoPayload,
  type PagoTerceroPayload,
  type PagoParafiscalPayload,
  type PagarParafiscalBody,
} from '../services/gapsMenoresService';

beforeEach(() => vi.clearAllMocks());

// ── 1) Ubicaciones de almacén ────────────────────────────────────────────────

describe('ubicacionesAlmacenService', () => {
  const BASE = '/almacenes/ubicaciones-almacen/';
  const payload: UbicacionAlmacenPayload = {
    id_almacen: 'alm-1',
    codigo_ubicacion: 'A-01',
    nombre_ubicacion: 'Estante A',
    tipo_ubicacion: 'ESTANTERIA',
    pasillo: '1',
    estante: 'A',
    nivel: null,
    posicion: null,
    capacidad_maxima: null,
    unidad_capacidad: null,
    activo: true,
    requiere_autorizacion: false,
    observaciones: null,
  };

  it('getAll sin params pega al endpoint base (array)', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_ubicacion: 'u1', id_almacen: 'alm-1' }]);
    const r = await ubicacionesAlmacenService.getAll();
    expect(get).toHaveBeenCalledWith(BASE);
    expect(r).toHaveLength(1);
  });

  it('getAll con almacén arma el querystring y filtra por almacén (paginada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [
        { id_ubicacion: 'u1', id_almacen: 'alm-1' },
        { id_ubicacion: 'u2', id_almacen: 'alm-2' },
      ],
    });
    const r = await ubicacionesAlmacenService.getAll({ almacen: 'alm-1' });
    expect(get).toHaveBeenCalledWith(`${BASE}?id_almacen=alm-1`);
    expect(r).toEqual([{ id_ubicacion: 'u1', id_almacen: 'alm-1' }]);
  });

  it('getAll normaliza respuesta inesperada a lista vacía', async () => {
    vi.mocked(get).mockResolvedValueOnce(null);
    expect(await ubicacionesAlmacenService.getAll()).toEqual([]);
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_ubicacion: 'u2' });
    await ubicacionesAlmacenService.create(payload);
    expect(post).toHaveBeenCalledWith(BASE, payload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id_ubicacion: 'u2' });
    await ubicacionesAlmacenService.update('u2', payload);
    expect(patch).toHaveBeenCalledWith(`${BASE}u2/`, payload);
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await ubicacionesAlmacenService.remove('u2');
    expect(del).toHaveBeenCalledWith(`${BASE}u2/`);
  });

  it('propaga el error del backend', async () => {
    vi.mocked(get).mockRejectedValueOnce(new Error('boom'));
    await expect(ubicacionesAlmacenService.getAll({ almacen: 'a' })).rejects.toThrow('boom');
  });
});

// ── 2) Movimientos internos de fondo ─────────────────────────────────────────

describe('movimientosInternosFondoService', () => {
  const BASE = '/tesoreria/movimientos-internos-fondo/';
  const payload: MovimientoInternoFondoPayload = {
    caja_origen: 'c1',
    caja_destino: 'c2',
    monto: '100.00',
    descripcion: 'traspaso',
    id_moneda: 'mon-1',
    referencia_externa: null,
  };

  it('getAll normaliza la lista paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id: 1 }] });
    const r = await movimientosInternosFondoService.getAll();
    expect(get).toHaveBeenCalledWith(BASE);
    expect(r).toEqual([{ id: 1 }]);
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id: 2 });
    await movimientosInternosFondoService.create(payload);
    expect(post).toHaveBeenCalledWith(BASE, payload);
  });

  it('remove borra por id (numérico y string)', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    await movimientosInternosFondoService.remove(7);
    expect(del).toHaveBeenCalledWith(`${BASE}7/`);
    await movimientosInternosFondoService.remove('9');
    expect(del).toHaveBeenCalledWith(`${BASE}9/`);
  });

  it('fetchCajasEmpresa arma el querystring por empresa', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_caja: 'c1', nombre: 'Caja 1' }]);
    const r = await fetchCajasEmpresa('e1');
    expect(get).toHaveBeenCalledWith('/finanzas/cajas/?empresa=e1');
    expect(r).toEqual([{ id_caja: 'c1', nombre: 'Caja 1' }]);
  });

  it('fetchCajasEmpresa normaliza respuesta vacía', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined);
    expect(await fetchCajasEmpresa('e1')).toEqual([]);
  });
});

// ── 3) Pagos de terceros ─────────────────────────────────────────────────────

describe('pagosTercerosService', () => {
  const BASE = '/finanzas/pagos-terceros/';
  const payload: PagoTerceroPayload = {
    id_proveedor: 'prov-1',
    id_moneda: 'mon-1',
    monto: '50.00',
    referencia_zelle: 'Z-1',
    fecha: '2026-06-27',
    concepto: 'cobro',
  };

  it('getAll sin filtros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_pago_tercero: 'p1' }]);
    await pagosTercerosService.getAll();
    expect(get).toHaveBeenCalledWith(BASE);
  });

  it('getAll arma estado + proveedor', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [] });
    await pagosTercerosService.getAll({ estado: 'pendiente', proveedor: 'prov-1' });
    expect(get).toHaveBeenCalledWith(`${BASE}?estado=pendiente&proveedor=prov-1`);
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_pago_tercero: 'p2' });
    await pagosTercerosService.create(payload);
    expect(post).toHaveBeenCalledWith(BASE, payload);
  });

  it('abonar postea cxp + descripcion (default vacía)', async () => {
    vi.mocked(post).mockResolvedValue({ id_pago_tercero: 'p1' });
    await pagosTercerosService.abonar('p1', 'cxp-1');
    expect(post).toHaveBeenCalledWith(`${BASE}p1/abonar/`, { cxp: 'cxp-1', descripcion: '' });
    await pagosTercerosService.abonar('p1', 'cxp-1', 'nota');
    expect(post).toHaveBeenCalledWith(`${BASE}p1/abonar/`, { cxp: 'cxp-1', descripcion: 'nota' });
  });

  it('solicitarReintegro postea body (con y sin)', async () => {
    vi.mocked(post).mockResolvedValue({ id_pago_tercero: 'p1' });
    await pagosTercerosService.solicitarReintegro('p1');
    expect(post).toHaveBeenCalledWith(`${BASE}p1/solicitar-reintegro/`, {});
    await pagosTercerosService.solicitarReintegro('p1', { comision: '5.00' });
    expect(post).toHaveBeenCalledWith(`${BASE}p1/solicitar-reintegro/`, { comision: '5.00' });
  });

  it('asociarProveedor, marcarReintegrado y anular postean a su acción', async () => {
    vi.mocked(post).mockResolvedValue({ id_pago_tercero: 'p1' });
    await pagosTercerosService.asociarProveedor('p1', 'prov-9');
    expect(post).toHaveBeenCalledWith(`${BASE}p1/asociar-proveedor/`, { proveedor: 'prov-9' });
    await pagosTercerosService.marcarReintegrado('p1');
    expect(post).toHaveBeenCalledWith(`${BASE}p1/marcar-reintegrado/`, {});
    await pagosTercerosService.anular('p1');
    expect(post).toHaveBeenCalledWith(`${BASE}p1/anular/`, {});
  });
});

// ── 4) Pagos parafiscales ────────────────────────────────────────────────────

describe('pagosParafiscalesService', () => {
  const BASE = '/fiscal/pagos-parafiscales/';
  const payload: PagoParafiscalPayload = {
    contribucion: 'contrib-1',
    periodo_año: 2026,
    periodo_mes: 6,
    monto: '300.00',
    id_moneda: 'mon-1',
  };

  it('getAll sin filtros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await pagosParafiscalesService.getAll();
    expect(get).toHaveBeenCalledWith(BASE);
  });

  it('getAll arma todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [] });
    await pagosParafiscalesService.getAll({
      estado: 'pendiente',
      contribucion: 'contrib-1',
      periodo_año: 2026,
      periodo_mes: 6,
    });
    expect(get).toHaveBeenCalledWith(
      `${BASE}?estado=pendiente&contribucion=contrib-1&periodo_a%C3%B1o=2026&periodo_mes=6`,
    );
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_pago_parafiscal: 'pp2' });
    await pagosParafiscalesService.create(payload);
    expect(post).toHaveBeenCalledWith(BASE, payload);
  });

  it('pagar postea el body (caja)', async () => {
    const body: PagarParafiscalBody = { metodo_pago: 'm1', caja: 'c1', referencia: 'PL-1' };
    vi.mocked(post).mockResolvedValueOnce({ id_pago_parafiscal: 'pp1' });
    await pagosParafiscalesService.pagar('pp1', body);
    expect(post).toHaveBeenCalledWith(`${BASE}pp1/pagar/`, body);
  });

  it('anular postea a su acción', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_pago_parafiscal: 'pp1' });
    await pagosParafiscalesService.anular('pp1');
    expect(post).toHaveBeenCalledWith(`${BASE}pp1/anular/`, {});
  });
});
