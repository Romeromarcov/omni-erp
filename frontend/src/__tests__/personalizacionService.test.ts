import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  personalizacionConfigService,
  type PersonalizacionConfigPayload,
} from '../services/personalizacionService';

const payload: PersonalizacionConfigPayload = {
  id_empresa: 'e1',
  descripcion: 'v2 con campos extra',
  config_yaml: 'entidades:\n  - Equipo',
  config_dict: { entidades: ['Equipo'] },
};

/** Construye un Error con status adjunto como lo hace services/api.buildError. */
function httpError(status: number, body = '{}'): Error {
  const e = new Error(body) as Error & { status?: number };
  e.status = status;
  return e;
}

describe('personalizacionConfigService.getAll', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_config: 'c1' }]);
    const r = await personalizacionConfigService.getAll();
    expect(get).toHaveBeenCalledWith('/personalizacion/configuraciones/');
    expect(r).toEqual([{ id_config: 'c1' }]);
  });

  it('con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await personalizacionConfigService.getAll({});
    expect(get).toHaveBeenCalledWith('/personalizacion/configuraciones/');
  });

  it('con empresa arma el querystring', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_config: 'c1' }] });
    const r = await personalizacionConfigService.getAll({ empresa: 'e1' });
    expect(get).toHaveBeenCalledWith('/personalizacion/configuraciones/?id_empresa=e1');
    expect(r).toEqual([{ id_config: 'c1' }]);
  });

  it('normaliza respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_config: 'c1' }] });
    expect((await personalizacionConfigService.getAll()).length).toBe(1);
  });

  it('ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await personalizacionConfigService.getAll()).toEqual([]);
  });

  it('propaga el error del backend', async () => {
    vi.mocked(get).mockRejectedValueOnce(new Error('500'));
    await expect(personalizacionConfigService.getAll()).rejects.toThrow('500');
  });
});

describe('personalizacionConfigService.historial', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sin empresa pega al endpoint historial', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_config: 'c1' }]);
    const r = await personalizacionConfigService.historial();
    expect(get).toHaveBeenCalledWith('/personalizacion/configuraciones/historial/');
    expect(r).toEqual([{ id_config: 'c1' }]);
  });

  it('con empresa arma el querystring empresa_id', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_config: 'c1' }]);
    await personalizacionConfigService.historial('e1');
    expect(get).toHaveBeenCalledWith(
      '/personalizacion/configuraciones/historial/?empresa_id=e1',
    );
  });

  it('normaliza respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_config: 'c1' }, { id_config: 'c2' }] });
    expect((await personalizacionConfigService.historial('e1')).length).toBe(2);
  });

  it('ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as never);
    expect(await personalizacionConfigService.historial('e1')).toEqual([]);
  });
});

describe('personalizacionConfigService.activa', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sin empresa pega al endpoint activa', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_config: 'c1', activo: true });
    const r = await personalizacionConfigService.activa();
    expect(get).toHaveBeenCalledWith('/personalizacion/configuraciones/activa/');
    expect(r).toEqual({ id_config: 'c1', activo: true });
  });

  it('con empresa arma el querystring empresa_id', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_config: 'c1' });
    await personalizacionConfigService.activa('e1');
    expect(get).toHaveBeenCalledWith(
      '/personalizacion/configuraciones/activa/?empresa_id=e1',
    );
  });

  it('404 (sin config activa) devuelve null', async () => {
    vi.mocked(get).mockRejectedValueOnce(httpError(404, '{"error":"No hay configuración activa"}'));
    expect(await personalizacionConfigService.activa('e1')).toBeNull();
  });

  it('propaga errores que NO son 404', async () => {
    vi.mocked(get).mockRejectedValueOnce(httpError(500, 'boom'));
    await expect(personalizacionConfigService.activa('e1')).rejects.toThrow('boom');
  });

  it('propaga un error sin status (fallo de red)', async () => {
    vi.mocked(get).mockRejectedValueOnce(new Error('network'));
    await expect(personalizacionConfigService.activa()).rejects.toThrow('network');
  });
});

describe('personalizacionConfigService — getById / create / update / remove', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_config: 'c1' });
    await personalizacionConfigService.getById('c1');
    expect(get).toHaveBeenCalledWith('/personalizacion/configuraciones/c1/');
  });

  it('create pega al endpoint con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_config: 'c2' });
    await personalizacionConfigService.create(payload);
    expect(post).toHaveBeenCalledWith('/personalizacion/configuraciones/', payload);
  });

  it('update pega al detalle con el payload', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id_config: 'c1' });
    await personalizacionConfigService.update('c1', payload);
    expect(patch).toHaveBeenCalledWith('/personalizacion/configuraciones/c1/', payload);
  });

  it('remove pega al detalle', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await personalizacionConfigService.remove('c1');
    expect(del).toHaveBeenCalledWith('/personalizacion/configuraciones/c1/');
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('regla'));
    await expect(personalizacionConfigService.create(payload)).rejects.toThrow('regla');
  });

  it('remove propaga el error del backend', async () => {
    vi.mocked(del).mockRejectedValueOnce(new Error('no encontrado'));
    await expect(personalizacionConfigService.remove('c1')).rejects.toThrow('no encontrado');
  });
});

describe('personalizacionConfigService.activar', () => {
  beforeEach(() => vi.clearAllMocks());

  it('pega al endpoint activar con cuerpo vacío', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_config: 'c1', activo: true });
    const r = await personalizacionConfigService.activar('c1');
    expect(post).toHaveBeenCalledWith('/personalizacion/configuraciones/c1/activar/', {});
    expect(r).toEqual({ id_config: 'c1', activo: true });
  });

  it('propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('400'));
    await expect(personalizacionConfigService.activar('c1')).rejects.toThrow('400');
  });
});
