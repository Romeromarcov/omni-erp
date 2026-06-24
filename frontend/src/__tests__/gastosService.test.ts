import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  categoriasGastoService,
  gastosService,
  detalleGastoService,
  reembolsosGastoService,
  type CategoriaGastoPayload,
  type GastoPayload,
  type DetalleGastoPayload,
  type ReembolsoGastoPayload,
} from '../services/gastosService';

const categoriaPayload: CategoriaGastoPayload = {
  id_empresa: 'e1',
  nombre_categoria: 'Servicios',
  descripcion: 'Gastos de servicios',
  id_cuenta_contable: 'cta-1',
  requiere_factura: true,
  activo: true,
};

const gastoPayload: GastoPayload = {
  id_empresa: 'e1',
  fecha_gasto: '2026-06-24',
  descripcion: 'Compra de papelería',
  monto: '100.00',
  monto_iva: '16.00',
  id_moneda: 'm1',
  id_categoria_gasto: 'cat-1',
  id_proveedor: null,
  tiene_factura: true,
  numero_factura: 'F-001',
};

const detallePayload: DetalleGastoPayload = {
  id_gasto: 'g1',
  id_cuenta_contable: 'cta-1',
  descripcion: 'Línea 1',
  monto: '50.00',
  monto_iva: '8.00',
};

const reembolsoPayload: ReembolsoGastoPayload = {
  id_empresa: 'e1',
  id_gasto: 'g1',
  monto_reembolso: '100.00',
  fecha_reembolso: '2026-06-24',
  id_moneda: 'm1',
  id_metodo_pago: 'mp1',
  estado_reembolso: 'PENDIENTE',
};

describe('categoriasGastoService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con empresa y search', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_categoria_gasto: 'c1' }] });
    const r = await categoriasGastoService.getAll({ empresa: 'e1', search: 'serv' });
    expect(get).toHaveBeenCalledWith('/gastos/categorias-gasto/?empresa=e1&search=serv');
    expect(r).toEqual([{ id_categoria_gasto: 'c1' }]);
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_categoria_gasto: 'c1' }]);
    await categoriasGastoService.getAll();
    expect(get).toHaveBeenCalledWith('/gastos/categorias-gasto/');
  });

  it('getAll con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await categoriasGastoService.getAll({});
    expect(get).toHaveBeenCalledWith('/gastos/categorias-gasto/');
  });

  it('getAll solo con empresa', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await categoriasGastoService.getAll({ empresa: 'e1' });
    expect(get).toHaveBeenCalledWith('/gastos/categorias-gasto/?empresa=e1');
  });

  it('getAll solo con search', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await categoriasGastoService.getAll({ search: 'serv' });
    expect(get).toHaveBeenCalledWith('/gastos/categorias-gasto/?search=serv');
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await categoriasGastoService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_categoria_gasto: 'c1' });
    await categoriasGastoService.getById('c1');
    expect(get).toHaveBeenCalledWith('/gastos/categorias-gasto/c1/');
  });

  it('activas normaliza paginado', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_categoria_gasto: 'c1' }] });
    const r = await categoriasGastoService.activas();
    expect(get).toHaveBeenCalledWith('/gastos/categorias-gasto/activas/');
    expect(r).toEqual([{ id_categoria_gasto: 'c1' }]);
  });

  it('activas normaliza array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_categoria_gasto: 'c1' }]);
    expect((await categoriasGastoService.activas()).length).toBe(1);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_categoria_gasto: 'c1' });
    await categoriasGastoService.create(categoriaPayload);
    expect(post).toHaveBeenCalledWith('/gastos/categorias-gasto/', categoriaPayload);

    vi.mocked(patch).mockResolvedValue({ id_categoria_gasto: 'c1' });
    await categoriasGastoService.update('c1', categoriaPayload);
    expect(patch).toHaveBeenCalledWith('/gastos/categorias-gasto/c1/', categoriaPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await categoriasGastoService.remove('c1');
    expect(del).toHaveBeenCalledWith('/gastos/categorias-gasto/c1/');
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('boom'));
    await expect(categoriasGastoService.create(categoriaPayload)).rejects.toThrow('boom');
  });
});

describe('gastosService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_gasto: 'g1' }] });
    const r = await gastosService.getAll({
      empresa: 'e1',
      estado: 'APROBADO',
      categoria: 'cat-1',
      search: 'pap',
    });
    expect(get).toHaveBeenCalledWith(
      '/gastos/gastos/?empresa=e1&estado_gasto=APROBADO&id_categoria_gasto=cat-1&search=pap',
    );
    expect(r).toEqual([{ id_gasto: 'g1' }]);
  });

  it('getAll sin parámetros', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await gastosService.getAll();
    expect(get).toHaveBeenCalledWith('/gastos/gastos/');
  });

  it('getAll con objeto vacío', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await gastosService.getAll({});
    expect(get).toHaveBeenCalledWith('/gastos/gastos/');
  });

  it('getAll solo con estado', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await gastosService.getAll({ estado: 'PENDIENTE_APROBACION' });
    expect(get).toHaveBeenCalledWith('/gastos/gastos/?estado_gasto=PENDIENTE_APROBACION');
  });

  it('getAll solo con categoria', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await gastosService.getAll({ categoria: 'cat-1' });
    expect(get).toHaveBeenCalledWith('/gastos/gastos/?id_categoria_gasto=cat-1');
  });

  it('getAll solo con search', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await gastosService.getAll({ search: 'pap' });
    expect(get).toHaveBeenCalledWith('/gastos/gastos/?search=pap');
  });

  it('getById', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_gasto: 'g1' });
    await gastosService.getById('g1');
    expect(get).toHaveBeenCalledWith('/gastos/gastos/g1/');
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_gasto: 'g1' });
    await gastosService.create(gastoPayload);
    expect(post).toHaveBeenCalledWith('/gastos/gastos/', gastoPayload);

    vi.mocked(patch).mockResolvedValue({ id_gasto: 'g1' });
    await gastosService.update('g1', gastoPayload);
    expect(patch).toHaveBeenCalledWith('/gastos/gastos/g1/', gastoPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await gastosService.remove('g1');
    expect(del).toHaveBeenCalledWith('/gastos/gastos/g1/');
  });

  it('aprobar postea cuerpo vacío', async () => {
    vi.mocked(post).mockResolvedValue({ id_gasto: 'g1', estado_gasto: 'APROBADO' });
    await gastosService.aprobar('g1');
    expect(post).toHaveBeenCalledWith('/gastos/gastos/g1/aprobar/', {});
  });

  it('aprobar propaga error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('sin respaldo'));
    await expect(gastosService.aprobar('g1')).rejects.toThrow('sin respaldo');
  });

  it('rechazar con motivo lo incluye en el cuerpo', async () => {
    vi.mocked(post).mockResolvedValue({ id_gasto: 'g1', estado_gasto: 'RECHAZADO' });
    await gastosService.rechazar('g1', 'sin justificación');
    expect(post).toHaveBeenCalledWith('/gastos/gastos/g1/rechazar/', { motivo: 'sin justificación' });
  });

  it('rechazar sin motivo manda cuerpo vacío', async () => {
    vi.mocked(post).mockResolvedValue({ id_gasto: 'g1' });
    await gastosService.rechazar('g1');
    expect(post).toHaveBeenCalledWith('/gastos/gastos/g1/rechazar/', {});
  });

  it('resumenPorCategoria con empresa codifica el id', async () => {
    vi.mocked(get).mockResolvedValueOnce({ resumen_por_categoria: [], total_general: 0 });
    await gastosService.resumenPorCategoria('e 1');
    expect(get).toHaveBeenCalledWith('/gastos/gastos/resumen_por_categoria/?empresa_id=e%201');
  });

  it('resumenPorCategoria sin empresa pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce({ resumen_por_categoria: [], total_general: 0 });
    await gastosService.resumenPorCategoria();
    expect(get).toHaveBeenCalledWith('/gastos/gastos/resumen_por_categoria/');
  });

  it('pendientesAprobacion normaliza paginado', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_gasto: 'g1' }] });
    const r = await gastosService.pendientesAprobacion();
    expect(get).toHaveBeenCalledWith('/gastos/gastos/pendientes_aprobacion/');
    expect(r).toEqual([{ id_gasto: 'g1' }]);
  });

  it('pendientesAprobacion normaliza array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_gasto: 'g1' }, { id_gasto: 'g2' }]);
    expect((await gastosService.pendientesAprobacion()).length).toBe(2);
  });
});

describe('detalleGastoService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll filtra por gasto en el cliente y codifica el id', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_detalle_gasto: 'd1', id_gasto: 'g1' },
      { id_detalle_gasto: 'd2', id_gasto: 'otro' },
    ]);
    const r = await detalleGastoService.getAll({ gasto: 'g1' });
    expect(get).toHaveBeenCalledWith('/gastos/detalles-gasto/?id_gasto=g1');
    expect(r.map((d) => d.id_detalle_gasto)).toEqual(['d1']);
  });

  it('getAll filtra sobre respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [
        { id_detalle_gasto: 'd1', id_gasto: 'g1' },
        { id_detalle_gasto: 'd2', id_gasto: 'otro' },
      ],
    });
    const r = await detalleGastoService.getAll({ gasto: 'g1' });
    expect(r.map((d) => d.id_detalle_gasto)).toEqual(['d1']);
  });

  it('getAll sin gasto devuelve la lista completa', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_detalle_gasto: 'd1', id_gasto: 'g1' }]);
    const r = await detalleGastoService.getAll();
    expect(get).toHaveBeenCalledWith('/gastos/detalles-gasto/');
    expect(r.length).toBe(1);
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_gasto: 'd1' });
    await detalleGastoService.create(detallePayload);
    expect(post).toHaveBeenCalledWith('/gastos/detalles-gasto/', detallePayload);

    vi.mocked(patch).mockResolvedValue({ id_detalle_gasto: 'd1' });
    await detalleGastoService.update('d1', detallePayload);
    expect(patch).toHaveBeenCalledWith('/gastos/detalles-gasto/d1/', detallePayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await detalleGastoService.remove('d1');
    expect(del).toHaveBeenCalledWith('/gastos/detalles-gasto/d1/');
  });

  it('create propaga el error', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('boom'));
    await expect(detalleGastoService.create(detallePayload)).rejects.toThrow('boom');
  });
});

describe('reembolsosGastoService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma querystring con empresa y estado', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_reembolso: 'r1' }] });
    const r = await reembolsosGastoService.getAll({ empresa: 'e1', estado: 'PENDIENTE' });
    expect(get).toHaveBeenCalledWith(
      '/gastos/reembolsos-gasto/?empresa=e1&estado_reembolso=PENDIENTE',
    );
    expect(r).toEqual([{ id_reembolso: 'r1' }]);
  });

  it('getAll sin parámetros', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await reembolsosGastoService.getAll();
    expect(get).toHaveBeenCalledWith('/gastos/reembolsos-gasto/');
  });

  it('getAll con objeto vacío', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await reembolsosGastoService.getAll({});
    expect(get).toHaveBeenCalledWith('/gastos/reembolsos-gasto/');
  });

  it('getAll solo con estado', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await reembolsosGastoService.getAll({ estado: 'PAGADO' });
    expect(get).toHaveBeenCalledWith('/gastos/reembolsos-gasto/?estado_reembolso=PAGADO');
  });

  it('getById', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_reembolso: 'r1' });
    await reembolsosGastoService.getById('r1');
    expect(get).toHaveBeenCalledWith('/gastos/reembolsos-gasto/r1/');
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_reembolso: 'r1' });
    await reembolsosGastoService.create(reembolsoPayload);
    expect(post).toHaveBeenCalledWith('/gastos/reembolsos-gasto/', reembolsoPayload);

    vi.mocked(patch).mockResolvedValue({ id_reembolso: 'r1' });
    await reembolsosGastoService.update('r1', reembolsoPayload);
    expect(patch).toHaveBeenCalledWith('/gastos/reembolsos-gasto/r1/', reembolsoPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await reembolsosGastoService.remove('r1');
    expect(del).toHaveBeenCalledWith('/gastos/reembolsos-gasto/r1/');
  });

  it('procesarPago postea cuerpo vacío', async () => {
    vi.mocked(post).mockResolvedValue({ id_reembolso: 'r1', estado_reembolso: 'PAGADO' });
    await reembolsosGastoService.procesarPago('r1');
    expect(post).toHaveBeenCalledWith('/gastos/reembolsos-gasto/r1/procesar_pago/', {});
  });

  it('anular postea cuerpo vacío', async () => {
    vi.mocked(post).mockResolvedValue({ id_reembolso: 'r1', estado_reembolso: 'ANULADO' });
    await reembolsosGastoService.anular('r1');
    expect(post).toHaveBeenCalledWith('/gastos/reembolsos-gasto/r1/anular/', {});
  });

  it('anular propaga error del backend (reembolso pagado)', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('No se puede anular un reembolso ya pagado'));
    await expect(reembolsosGastoService.anular('r1')).rejects.toThrow('ya pagado');
  });

  it('pendientesPago normaliza paginado', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_reembolso: 'r1' }] });
    const r = await reembolsosGastoService.pendientesPago();
    expect(get).toHaveBeenCalledWith('/gastos/reembolsos-gasto/pendientes_pago/');
    expect(r).toEqual([{ id_reembolso: 'r1' }]);
  });

  it('pendientesPago normaliza array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_reembolso: 'r1' }]);
    expect((await reembolsosGastoService.pendientesPago()).length).toBe(1);
  });
});
