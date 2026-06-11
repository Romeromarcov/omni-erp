import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

import { get, post } from '../services/api';
import {
  getProveedores,
  getConectores,
  getConector,
  crearConector,
  testConector,
  triggerSync,
  exportarConector,
  getJobsDeConector,
  getJobs,
  getIntegrationHubStatus,
  type ConectorInstanciaCreate,
} from '../services/integrationHubService';

const mockedGet = vi.mocked(get);
const mockedPost = vi.mocked(post);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('integrationHubService — llamadas al API', () => {
  it('getProveedores pide el listado de proveedores', async () => {
    mockedGet.mockResolvedValueOnce({ count: 0, results: [] });
    await getProveedores();
    expect(mockedGet).toHaveBeenCalledWith('/integration-hub/proveedores/');
  });

  it('getConectores pide el listado de instancias', async () => {
    mockedGet.mockResolvedValueOnce({ count: 0, results: [] });
    await getConectores();
    expect(mockedGet).toHaveBeenCalledWith('/integration-hub/instancias/');
  });

  it('getConector pide la instancia por id', async () => {
    mockedGet.mockResolvedValueOnce({ id_conector: 'abc' });
    await getConector('abc');
    expect(mockedGet).toHaveBeenCalledWith('/integration-hub/instancias/abc/');
  });

  it('crearConector hace POST con el payload', async () => {
    const data = {
      id_proveedor: 'p1',
      nombre: 'Sheets',
      configuracion: {
        service_account: { client_email: 'svc@p.iam.gserviceaccount.com' },
        source_instancia_id: 'origen-1',
      },
      entidades_activas: ['contactos'],
    } as unknown as ConectorInstanciaCreate;
    mockedPost.mockResolvedValueOnce({ id_conector: 'nuevo' });
    await crearConector(data);
    expect(mockedPost).toHaveBeenCalledWith('/integration-hub/instancias/', data);
  });

  it('testConector hace POST a la acción test', async () => {
    mockedPost.mockResolvedValueOnce({ success: true });
    await testConector('abc');
    expect(mockedPost).toHaveBeenCalledWith('/integration-hub/instancias/abc/test/', {});
  });

  it('triggerSync envía la entidad a sincronizar', async () => {
    mockedPost.mockResolvedValueOnce({ job_id: 'j1' });
    await triggerSync('abc', 'contactos');
    expect(mockedPost).toHaveBeenCalledWith('/integration-hub/instancias/abc/sync/', {
      tipo_entidad: 'contactos',
    });
  });

  it('getJobsDeConector pide los jobs de la instancia', async () => {
    mockedGet.mockResolvedValueOnce({ count: 0, results: [] });
    await getJobsDeConector('abc');
    expect(mockedGet).toHaveBeenCalledWith('/integration-hub/instancias/abc/jobs/');
  });

  it('getIntegrationHubStatus pide el estado general', async () => {
    mockedGet.mockResolvedValueOnce({ conectores_activos: 0 });
    await getIntegrationHubStatus();
    expect(mockedGet).toHaveBeenCalledWith('/integration-hub/status/');
  });
});

describe('integrationHubService.exportarConector — contrato del endpoint', () => {
  it('sin opciones envía body vacío (usa entidades_activas, incremental)', async () => {
    mockedPost.mockResolvedValueOnce({ mensaje: 'ok', task_id: 't1' });
    const res = await exportarConector('abc');
    expect(mockedPost).toHaveBeenCalledWith('/integration-hub/instancias/abc/exportar/', {});
    expect(res).toEqual({ mensaje: 'ok', task_id: 't1' });
  });

  it('con tipos y full arma el body del contrato', async () => {
    mockedPost.mockResolvedValueOnce({ mensaje: 'ok', task_id: 't2' });
    await exportarConector('abc', { tipos: ['contactos', 'productos'], full: true });
    expect(mockedPost).toHaveBeenCalledWith('/integration-hub/instancias/abc/exportar/', {
      tipos: ['contactos', 'productos'],
      full: true,
    });
  });

  it('tipos null se omite del body (no se envía null)', async () => {
    mockedPost.mockResolvedValueOnce({ mensaje: 'ok', task_id: 't3' });
    await exportarConector('abc', { tipos: null, full: false });
    expect(mockedPost).toHaveBeenCalledWith('/integration-hub/instancias/abc/exportar/', {
      full: false,
    });
  });
});

describe('integrationHubService.getJobs — filtros por querystring', () => {
  it('sin params no agrega querystring', async () => {
    mockedGet.mockResolvedValueOnce({ count: 0, results: [] });
    await getJobs();
    expect(mockedGet).toHaveBeenCalledWith('/integration-hub/jobs/');
  });

  it('filtra por instancia y estado, omitiendo valores vacíos', async () => {
    mockedGet.mockResolvedValueOnce({ count: 0, results: [] });
    await getJobs({ instancia: 'abc', estado: 'completado', tipo_entidad: '' });
    expect(mockedGet).toHaveBeenCalledWith(
      '/integration-hub/jobs/?instancia=abc&estado=completado',
    );
  });
});
