import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  configuracionIntegracionService,
  mapeoCampoService,
  logsIntegracionService,
  type ConfiguracionIntegracionPayload,
  type MapeoCampoPayload,
} from '../services/integracionB2bService';

const configPayload: ConfiguracionIntegracionPayload = {
  id_empresa: 'e1',
  nombre_integracion: 'SAP B2B',
  tipo_integracion: 'REST',
  url_endpoint: 'https://api.ejemplo.com',
  credenciales_json: { token: 'abc' },
  formato_datos: 'JSON',
  activo: true,
};

const mapeoPayload: MapeoCampoPayload = {
  id_configuracion_integracion: 'cfg1',
  nombre_campo_interno: 'razon_social',
  nombre_campo_externo: 'CompanyName',
  activo: true,
};

describe('configuracionIntegracionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_configuracion: 'cfg1' }]);
    const r = await configuracionIntegracionService.getAll();
    expect(get).toHaveBeenCalledWith('/integracion-b2b/configuracion-integracion/');
    expect(r).toEqual([{ id_configuracion: 'cfg1' }]);
  });

  it('getAll con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await configuracionIntegracionService.getAll({});
    expect(get).toHaveBeenCalledWith('/integracion-b2b/configuracion-integracion/');
  });

  it('getAll con empresa arma el querystring', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_configuracion: 'cfg1' }] });
    const r = await configuracionIntegracionService.getAll({ empresa: 'e1' });
    expect(get).toHaveBeenCalledWith(
      '/integracion-b2b/configuracion-integracion/?id_empresa=e1',
    );
    expect(r).toEqual([{ id_configuracion: 'cfg1' }]);
  });

  it('getAll normaliza respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_configuracion: 'cfg1' }] });
    expect((await configuracionIntegracionService.getAll()).length).toBe(1);
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await configuracionIntegracionService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_configuracion: 'cfg1' });
    await configuracionIntegracionService.getById('cfg1');
    expect(get).toHaveBeenCalledWith('/integracion-b2b/configuracion-integracion/cfg1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_configuracion: 'cfg1' });
    await configuracionIntegracionService.create(configPayload);
    expect(post).toHaveBeenCalledWith(
      '/integracion-b2b/configuracion-integracion/',
      configPayload,
    );

    vi.mocked(patch).mockResolvedValue({ id_configuracion: 'cfg1' });
    await configuracionIntegracionService.update('cfg1', configPayload);
    expect(patch).toHaveBeenCalledWith(
      '/integracion-b2b/configuracion-integracion/cfg1/',
      configPayload,
    );

    vi.mocked(del).mockResolvedValue(undefined);
    await configuracionIntegracionService.remove('cfg1');
    expect(del).toHaveBeenCalledWith('/integracion-b2b/configuracion-integracion/cfg1/');
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('boom'));
    await expect(configuracionIntegracionService.create(configPayload)).rejects.toThrow(
      'boom',
    );
  });

  it('update propaga el error del backend', async () => {
    vi.mocked(patch).mockRejectedValueOnce(new Error('regla'));
    await expect(
      configuracionIntegracionService.update('cfg1', configPayload),
    ).rejects.toThrow('regla');
  });
});

describe('mapeoCampoService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll sin parámetros no filtra', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_mapeo_campo: 'm1', id_configuracion_integracion: 'cfg1' },
      { id_mapeo_campo: 'm2', id_configuracion_integracion: 'cfg2' },
    ]);
    const r = await mapeoCampoService.getAll();
    expect(get).toHaveBeenCalledWith('/integracion-b2b/mapeo-campos/');
    expect(r.length).toBe(2);
  });

  it('getAll con objeto vacío', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await mapeoCampoService.getAll({});
    expect(get).toHaveBeenCalledWith('/integracion-b2b/mapeo-campos/');
  });

  it('getAll con configuración arma el querystring y filtra por configuración', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_mapeo_campo: 'm1', id_configuracion_integracion: 'cfg1' },
      { id_mapeo_campo: 'm2', id_configuracion_integracion: 'otro' },
    ]);
    const r = await mapeoCampoService.getAll({ configuracion: 'cfg1' });
    expect(get).toHaveBeenCalledWith(
      '/integracion-b2b/mapeo-campos/?id_configuracion_integracion=cfg1',
    );
    expect(r).toEqual([{ id_mapeo_campo: 'm1', id_configuracion_integracion: 'cfg1' }]);
  });

  it('getAll normaliza respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [{ id_mapeo_campo: 'm1', id_configuracion_integracion: 'cfg1' }],
    });
    const r = await mapeoCampoService.getAll({ configuracion: 'cfg1' });
    expect(r.length).toBe(1);
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as never);
    expect(await mapeoCampoService.getAll({ configuracion: 'cfg1' })).toEqual([]);
  });

  it('getById', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_mapeo_campo: 'm1' });
    await mapeoCampoService.getById('m1');
    expect(get).toHaveBeenCalledWith('/integracion-b2b/mapeo-campos/m1/');
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_mapeo_campo: 'm1' });
    await mapeoCampoService.create(mapeoPayload);
    expect(post).toHaveBeenCalledWith('/integracion-b2b/mapeo-campos/', mapeoPayload);

    vi.mocked(patch).mockResolvedValue({ id_mapeo_campo: 'm1' });
    await mapeoCampoService.update('m1', mapeoPayload);
    expect(patch).toHaveBeenCalledWith('/integracion-b2b/mapeo-campos/m1/', mapeoPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await mapeoCampoService.remove('m1');
    expect(del).toHaveBeenCalledWith('/integracion-b2b/mapeo-campos/m1/');
  });

  it('remove propaga el error del backend', async () => {
    vi.mocked(del).mockRejectedValueOnce(new Error('no encontrado'));
    await expect(mapeoCampoService.remove('m1')).rejects.toThrow('no encontrado');
  });
});

describe('logsIntegracionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll con configuración arma el querystring y filtra por configuración', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_log_integracion: 'l1', id_configuracion: 'cfg1' },
      { id_log_integracion: 'l2', id_configuracion: 'otro' },
    ]);
    const r = await logsIntegracionService.getAll({ configuracion: 'cfg1' });
    expect(get).toHaveBeenCalledWith(
      '/integracion-b2b/logs-integracion/?id_configuracion=cfg1',
    );
    expect(r).toEqual([{ id_log_integracion: 'l1', id_configuracion: 'cfg1' }]);
  });

  it('getAll sin parámetros no filtra', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_log_integracion: 'l1', id_configuracion: 'cfg1' },
      { id_log_integracion: 'l2', id_configuracion: 'cfg2' },
    ]);
    const r = await logsIntegracionService.getAll();
    expect(get).toHaveBeenCalledWith('/integracion-b2b/logs-integracion/');
    expect(r.length).toBe(2);
  });

  it('getAll con objeto vacío', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await logsIntegracionService.getAll({});
    expect(get).toHaveBeenCalledWith('/integracion-b2b/logs-integracion/');
  });

  it('getAll normaliza respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [{ id_log_integracion: 'l1', id_configuracion: 'cfg1' }],
    });
    const r = await logsIntegracionService.getAll({ configuracion: 'cfg1' });
    expect(r.length).toBe(1);
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await logsIntegracionService.getAll({ configuracion: 'cfg1' })).toEqual([]);
  });

  it('getById', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_log_integracion: 'l1' });
    await logsIntegracionService.getById('l1');
    expect(get).toHaveBeenCalledWith('/integracion-b2b/logs-integracion/l1/');
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_log_integracion: 'l1' });
    await logsIntegracionService.create({ tipo_transaccion: 'PUSH', estado_integracion: 'exitoso' });
    expect(post).toHaveBeenCalledWith('/integracion-b2b/logs-integracion/', {
      tipo_transaccion: 'PUSH',
      estado_integracion: 'exitoso',
    });

    vi.mocked(patch).mockResolvedValue({ id_log_integracion: 'l1' });
    await logsIntegracionService.update('l1', { estado_integracion: 'error' });
    expect(patch).toHaveBeenCalledWith('/integracion-b2b/logs-integracion/l1/', {
      estado_integracion: 'error',
    });

    vi.mocked(del).mockResolvedValue(undefined);
    await logsIntegracionService.remove('l1');
    expect(del).toHaveBeenCalledWith('/integracion-b2b/logs-integracion/l1/');
  });

  it('getAll propaga el error del backend', async () => {
    vi.mocked(get).mockRejectedValueOnce(new Error('500'));
    await expect(logsIntegracionService.getAll()).rejects.toThrow('500');
  });
});
