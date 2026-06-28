import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  postForm: vi.fn(),
}));

import { get, post, patch, del, postForm } from '../services/api';
import {
  listasPrecioService,
  detallesPrecioService,
  type ListaPrecioPayload,
  type DetallePrecioPayload,
} from '../services/listasPrecioService';

const listaPayload: ListaPrecioPayload = {
  nombre: 'Mayoreo',
  codigo: 'MAYOREO',
  id_moneda: 'm1',
  es_referencia: false,
  activo: true,
};

const detallePayload: DetallePrecioPayload = {
  id_lista: 'l1',
  id_producto: 'p1',
  precio: '15.5000',
  precio_minimo: '12.0000',
  vigente_desde: '2026-01-01',
  vigente_hasta: '2026-12-31',
  activo: true,
};

describe('listasPrecioService CRUD', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con activo y search', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_lista: 'l1' }] });
    const r = await listasPrecioService.getAll({ activo: true, search: 'may' });
    expect(get).toHaveBeenCalledWith('/ventas/listas-precio/?activo=true&search=may');
    expect(r).toEqual([{ id_lista: 'l1' }]);
  });

  it('getAll sin parámetros pega al endpoint base (rama array)', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_lista: 'l1' }]);
    const r = await listasPrecioService.getAll();
    expect(get).toHaveBeenCalledWith('/ventas/listas-precio/');
    expect(r).toEqual([{ id_lista: 'l1' }]);
  });

  it('getAll normaliza una respuesta vacía/no reconocida', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    const r = await listasPrecioService.getAll({ activo: false });
    expect(get).toHaveBeenCalledWith('/ventas/listas-precio/?activo=false');
    expect(r).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_lista: 'l1' });
    await listasPrecioService.getById('l1');
    expect(get).toHaveBeenCalledWith('/ventas/listas-precio/l1/');
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_lista: 'l2' });
    await listasPrecioService.create(listaPayload);
    expect(post).toHaveBeenCalledWith('/ventas/listas-precio/', listaPayload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_lista: 'l1' });
    await listasPrecioService.update('l1', listaPayload);
    expect(patch).toHaveBeenCalledWith('/ventas/listas-precio/l1/', listaPayload);
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    await listasPrecioService.remove('l1');
    expect(del).toHaveBeenCalledWith('/ventas/listas-precio/l1/');
  });
});

describe('listasPrecioService.importarMasivo', () => {
  beforeEach(() => vi.clearAllMocks());

  it('arma el FormData con el archivo y pega al endpoint de importación', async () => {
    vi.mocked(postForm).mockResolvedValue({
      lista: 'Mayoreo',
      creados: 2,
      actualizados: 1,
      errores: [],
      total_errores: 0,
    });
    const file = new File(['codigo_producto,precio\nP-1,10'], 'precios.csv', { type: 'text/csv' });
    const r = await listasPrecioService.importarMasivo('l1', file);

    expect(postForm).toHaveBeenCalledTimes(1);
    const [url, form] = vi.mocked(postForm).mock.calls[0];
    expect(url).toBe('/ventas/listas-precio/l1/importar-masivo/');
    expect(form).toBeInstanceOf(FormData);
    expect((form as FormData).get('archivo')).toBe(file);
    expect(r.creados).toBe(2);
  });

  it('propaga el error del backend (mensajeDeError)', async () => {
    vi.mocked(postForm).mockRejectedValue(new Error(JSON.stringify({ error: 'CSV inválido.' })));
    const file = new File([''], 'x.csv', { type: 'text/csv' });
    await expect(listasPrecioService.importarMasivo('l1', file)).rejects.toThrow();
  });
});

describe('detallesPrecioService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll filtra por lista en el querystring y en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_detalle: 'd1', id_lista: 'l1' },
      { id_detalle: 'd2', id_lista: 'otra' },
    ]);
    const r = await detallesPrecioService.getAll({ lista: 'l1' });
    expect(get).toHaveBeenCalledWith('/ventas/detalles-precio/?id_lista=l1');
    expect(r.map((d) => d.id_detalle)).toEqual(['d1']);
  });

  it('getAll sin lista no filtra (rama paginada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_detalle: 'd1', id_lista: 'l1' }] });
    const r = await detallesPrecioService.getAll({ activo: true });
    expect(get).toHaveBeenCalledWith('/ventas/detalles-precio/?activo=true');
    expect(r).toHaveLength(1);
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await detallesPrecioService.getAll();
    expect(get).toHaveBeenCalledWith('/ventas/detalles-precio/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle: 'd1' });
    await detallesPrecioService.create(detallePayload);
    expect(post).toHaveBeenCalledWith('/ventas/detalles-precio/', detallePayload);

    vi.mocked(patch).mockResolvedValue({ id_detalle: 'd1' });
    await detallesPrecioService.update('d1', detallePayload);
    expect(patch).toHaveBeenCalledWith('/ventas/detalles-precio/d1/', detallePayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await detallesPrecioService.remove('d1');
    expect(del).toHaveBeenCalledWith('/ventas/detalles-precio/d1/');
  });
});
