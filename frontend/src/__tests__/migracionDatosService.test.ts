import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  plantillasMigracionService,
  procesosMigracionService,
  detallesErrorMigracionService,
  type PlantillaMigracionPayload,
  type ProcesoMigracionPayload,
  type DetalleErrorMigracionPayload,
} from '../services/migracionDatosService';

const plantillaPayload: PlantillaMigracionPayload = {
  nombre_plantilla: 'Clientes CSV',
  modulo_destino: 'crm',
  modelo_destino: 'Cliente',
  formato_archivo: 'CSV',
  estructura_json: { columnas: ['nombre', 'rif'] },
  activo: true,
};

const procesoPayload: ProcesoMigracionPayload = {
  id_empresa: 'e1',
  id_plantilla_migracion: 'pl1',
  id_usuario_ejecutor: 'u1',
  estado_proceso: 'PENDIENTE',
  total_registros_procesados: 0,
  total_registros_exitosos: 0,
  total_registros_fallidos: 0,
  ruta_archivo_cargado: '/tmp/archivo.csv',
  ruta_archivo_errores: null,
};

const errorPayload: DetalleErrorMigracionPayload = {
  id_proceso_migracion: 'pr1',
  numero_fila_archivo: 3,
  campo_error: 'rif',
  mensaje_error: 'RIF inválido',
  datos_originales_json: { rif: 'XXX' },
};

describe('plantillasMigracionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_plantilla_migracion: 'pl1' }]);
    const r = await plantillasMigracionService.getAll();
    expect(get).toHaveBeenCalledWith('/migracion-datos/plantillas-migracion/');
    expect(r).toEqual([{ id_plantilla_migracion: 'pl1' }]);
  });

  it('getAll con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await plantillasMigracionService.getAll({});
    expect(get).toHaveBeenCalledWith('/migracion-datos/plantillas-migracion/');
  });

  it('getAll con activo=true arma el querystring', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_plantilla_migracion: 'pl1' }] });
    const r = await plantillasMigracionService.getAll({ activo: true });
    expect(get).toHaveBeenCalledWith('/migracion-datos/plantillas-migracion/?activo=true');
    expect(r).toEqual([{ id_plantilla_migracion: 'pl1' }]);
  });

  it('getAll con activo=false arma el querystring', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await plantillasMigracionService.getAll({ activo: false });
    expect(get).toHaveBeenCalledWith('/migracion-datos/plantillas-migracion/?activo=false');
  });

  it('getAll normaliza respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_plantilla_migracion: 'pl1' }] });
    expect((await plantillasMigracionService.getAll()).length).toBe(1);
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await plantillasMigracionService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_plantilla_migracion: 'pl1' });
    await plantillasMigracionService.getById('pl1');
    expect(get).toHaveBeenCalledWith('/migracion-datos/plantillas-migracion/pl1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_plantilla_migracion: 'pl1' });
    await plantillasMigracionService.create(plantillaPayload);
    expect(post).toHaveBeenCalledWith(
      '/migracion-datos/plantillas-migracion/',
      plantillaPayload,
    );

    vi.mocked(patch).mockResolvedValue({ id_plantilla_migracion: 'pl1' });
    await plantillasMigracionService.update('pl1', plantillaPayload);
    expect(patch).toHaveBeenCalledWith(
      '/migracion-datos/plantillas-migracion/pl1/',
      plantillaPayload,
    );

    vi.mocked(del).mockResolvedValue(undefined);
    await plantillasMigracionService.remove('pl1');
    expect(del).toHaveBeenCalledWith('/migracion-datos/plantillas-migracion/pl1/');
  });

  it('create propaga el 403 del backend (no superusuario)', async () => {
    const err = Object.assign(new Error(JSON.stringify({ detail: 'No autorizado.' })), {
      status: 403,
    });
    vi.mocked(post).mockRejectedValueOnce(err);
    await expect(plantillasMigracionService.create(plantillaPayload)).rejects.toThrow(
      /No autorizado/,
    );
  });

  it('update propaga el error genérico del backend', async () => {
    vi.mocked(patch).mockRejectedValueOnce(new Error('boom'));
    await expect(plantillasMigracionService.update('pl1', plantillaPayload)).rejects.toThrow(
      'boom',
    );
  });
});

describe('procesosMigracionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con empresa, plantilla y estado', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_proceso_migracion: 'pr1' }] });
    const r = await procesosMigracionService.getAll({
      empresa: 'e1',
      plantilla: 'pl1',
      estado: 'COMPLETADO',
    });
    expect(get).toHaveBeenCalledWith(
      '/migracion-datos/procesos-migracion/?id_empresa=e1&id_plantilla_migracion=pl1&estado_proceso=COMPLETADO',
    );
    expect(r).toEqual([{ id_proceso_migracion: 'pr1' }]);
  });

  it('getAll sin parámetros', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await procesosMigracionService.getAll();
    expect(get).toHaveBeenCalledWith('/migracion-datos/procesos-migracion/');
  });

  it('getAll con objeto vacío', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await procesosMigracionService.getAll({});
    expect(get).toHaveBeenCalledWith('/migracion-datos/procesos-migracion/');
  });

  it('getAll solo con empresa', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await procesosMigracionService.getAll({ empresa: 'e1' });
    expect(get).toHaveBeenCalledWith('/migracion-datos/procesos-migracion/?id_empresa=e1');
  });

  it('getAll solo con estado', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await procesosMigracionService.getAll({ estado: 'FALLIDO' });
    expect(get).toHaveBeenCalledWith(
      '/migracion-datos/procesos-migracion/?estado_proceso=FALLIDO',
    );
  });

  it('getAll normaliza array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_proceso_migracion: 'pr1' }]);
    expect((await procesosMigracionService.getAll()).length).toBe(1);
  });

  it('getById', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_proceso_migracion: 'pr1' });
    await procesosMigracionService.getById('pr1');
    expect(get).toHaveBeenCalledWith('/migracion-datos/procesos-migracion/pr1/');
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_proceso_migracion: 'pr1' });
    await procesosMigracionService.create(procesoPayload);
    expect(post).toHaveBeenCalledWith('/migracion-datos/procesos-migracion/', procesoPayload);

    vi.mocked(patch).mockResolvedValue({ id_proceso_migracion: 'pr1' });
    await procesosMigracionService.update('pr1', procesoPayload);
    expect(patch).toHaveBeenCalledWith(
      '/migracion-datos/procesos-migracion/pr1/',
      procesoPayload,
    );

    vi.mocked(del).mockResolvedValue(undefined);
    await procesosMigracionService.remove('pr1');
    expect(del).toHaveBeenCalledWith('/migracion-datos/procesos-migracion/pr1/');
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('regla'));
    await expect(procesosMigracionService.create(procesoPayload)).rejects.toThrow('regla');
  });
});

describe('detallesErrorMigracionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll con proceso arma el querystring y filtra por proceso', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_detalle_error: 'd1', id_proceso_migracion: 'pr1' },
      { id_detalle_error: 'd2', id_proceso_migracion: 'otro' },
    ]);
    const r = await detallesErrorMigracionService.getAll({ proceso: 'pr1' });
    expect(get).toHaveBeenCalledWith(
      '/migracion-datos/detalles-error-migracion/?id_proceso_migracion=pr1',
    );
    expect(r).toEqual([{ id_detalle_error: 'd1', id_proceso_migracion: 'pr1' }]);
  });

  it('getAll sin parámetros no filtra', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_detalle_error: 'd1', id_proceso_migracion: 'pr1' },
      { id_detalle_error: 'd2', id_proceso_migracion: 'pr2' },
    ]);
    const r = await detallesErrorMigracionService.getAll();
    expect(get).toHaveBeenCalledWith('/migracion-datos/detalles-error-migracion/');
    expect(r.length).toBe(2);
  });

  it('getAll con objeto vacío', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await detallesErrorMigracionService.getAll({});
    expect(get).toHaveBeenCalledWith('/migracion-datos/detalles-error-migracion/');
  });

  it('getAll normaliza respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [{ id_detalle_error: 'd1', id_proceso_migracion: 'pr1' }],
    });
    const r = await detallesErrorMigracionService.getAll({ proceso: 'pr1' });
    expect(r.length).toBe(1);
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as never);
    expect(await detallesErrorMigracionService.getAll({ proceso: 'pr1' })).toEqual([]);
  });

  it('getById', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_detalle_error: 'd1' });
    await detallesErrorMigracionService.getById('d1');
    expect(get).toHaveBeenCalledWith('/migracion-datos/detalles-error-migracion/d1/');
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_error: 'd1' });
    await detallesErrorMigracionService.create(errorPayload);
    expect(post).toHaveBeenCalledWith(
      '/migracion-datos/detalles-error-migracion/',
      errorPayload,
    );

    vi.mocked(patch).mockResolvedValue({ id_detalle_error: 'd1' });
    await detallesErrorMigracionService.update('d1', errorPayload);
    expect(patch).toHaveBeenCalledWith(
      '/migracion-datos/detalles-error-migracion/d1/',
      errorPayload,
    );

    vi.mocked(del).mockResolvedValue(undefined);
    await detallesErrorMigracionService.remove('d1');
    expect(del).toHaveBeenCalledWith('/migracion-datos/detalles-error-migracion/d1/');
  });

  it('remove propaga el error del backend', async () => {
    vi.mocked(del).mockRejectedValueOnce(new Error('no encontrado'));
    await expect(detallesErrorMigracionService.remove('d1')).rejects.toThrow('no encontrado');
  });
});
