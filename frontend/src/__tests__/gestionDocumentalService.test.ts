import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  postForm: vi.fn(),
  fetcher: vi.fn(),
}));

import { get, post, patch, del, postForm, fetcher } from '../services/api';
import {
  carpetasService,
  documentosService,
  vinculosDocumentoService,
  permisosDocumentoService,
  type CarpetaPayload,
  type VinculoDocumentoPayload,
  type PermisoDocumentoPayload,
} from '../services/gestionDocumentalService';

beforeEach(() => vi.clearAllMocks());

// ── Carpetas ──────────────────────────────────────────────────────────────────

describe('carpetasService', () => {
  it('getAll arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_carpeta: 'c1' }] });
    const r = await carpetasService.getAll({ empresa: 'e1', padre: 'p1', search: 'fac' });
    expect(get).toHaveBeenCalledWith(
      '/gestion-documental/carpetas/?id_empresa=e1&id_carpeta_padre=p1&search=fac',
    );
    expect(r).toEqual([{ id_carpeta: 'c1' }]);
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await carpetasService.getAll();
    expect(get).toHaveBeenCalledWith('/gestion-documental/carpetas/');
  });

  it('getAll con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await carpetasService.getAll({});
    expect(get).toHaveBeenCalledWith('/gestion-documental/carpetas/');
  });

  it('getAll normaliza un array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_carpeta: 'c1' }, { id_carpeta: 'c2' }]);
    expect((await carpetasService.getAll()).length).toBe(2);
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await carpetasService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_carpeta: 'c1' });
    await carpetasService.getById('c1');
    expect(get).toHaveBeenCalledWith('/gestion-documental/carpetas/c1/');
  });

  it('create envía el payload', async () => {
    const payload: CarpetaPayload = {
      id_empresa: 'e1',
      nombre_carpeta: 'Facturas',
      id_carpeta_padre: null,
      es_publica: false,
      activo: true,
      id_usuario_creacion: 'u1',
    };
    vi.mocked(post).mockResolvedValueOnce({ id_carpeta: 'c1' });
    await carpetasService.create(payload);
    expect(post).toHaveBeenCalledWith('/gestion-documental/carpetas/', payload);
  });

  it('update envía PATCH', async () => {
    const payload: CarpetaPayload = {
      id_empresa: 'e1',
      nombre_carpeta: 'Otra',
      id_carpeta_padre: 'p1',
      es_publica: true,
      activo: true,
      id_usuario_creacion: 'u1',
    };
    vi.mocked(patch).mockResolvedValueOnce({ id_carpeta: 'c1' });
    await carpetasService.update('c1', payload);
    expect(patch).toHaveBeenCalledWith('/gestion-documental/carpetas/c1/', payload);
  });

  it('remove pega al DELETE', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await carpetasService.remove('c1');
    expect(del).toHaveBeenCalledWith('/gestion-documental/carpetas/c1/');
  });
});

// ── Documentos ────────────────────────────────────────────────────────────────

describe('documentosService.getAll', () => {
  it('arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_documento: 'd1' }] });
    await documentosService.getAll({ empresa: 'e1', carpeta: 'c1', search: 'pdf' });
    expect(get).toHaveBeenCalledWith(
      '/gestion-documental/documentos/?id_empresa=e1&id_carpeta=c1&search=pdf',
    );
  });

  it('sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await documentosService.getAll();
    expect(get).toHaveBeenCalledWith('/gestion-documental/documentos/');
  });

  it('con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await documentosService.getAll({});
    expect(get).toHaveBeenCalledWith('/gestion-documental/documentos/');
  });

  it('normaliza array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_documento: 'd1' }]);
    expect((await documentosService.getAll()).length).toBe(1);
  });

  it('ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as never);
    expect(await documentosService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_documento: 'd1' });
    await documentosService.getById('d1');
    expect(get).toHaveBeenCalledWith('/gestion-documental/documentos/d1/');
  });
});

describe('documentosService.subir', () => {
  it('arma un FormData con el archivo y todos los metadatos', async () => {
    vi.mocked(postForm).mockResolvedValueOnce({ id_documento: 'd1' });
    const archivo = new File(['contenido'], 'factura.pdf', { type: 'application/pdf' });
    await documentosService.subir({
      empresaId: 'e1',
      archivo,
      carpetaId: 'c1',
      descripcion: 'Factura enero',
      carpetaNombre: 'fiscales',
    });
    expect(postForm).toHaveBeenCalledTimes(1);
    const [endpoint, form] = vi.mocked(postForm).mock.calls[0];
    expect(endpoint).toBe('/gestion-documental/documentos/subir/');
    const fd = form as FormData;
    expect(fd).toBeInstanceOf(FormData);
    expect((fd.get('archivo') as File).name).toBe('factura.pdf');
    expect(fd.get('empresa_id')).toBe('e1');
    expect(fd.get('carpeta_id')).toBe('c1');
    expect(fd.get('descripcion')).toBe('Factura enero');
    expect(fd.get('carpeta_nombre')).toBe('fiscales');
  });

  it('omite los campos opcionales no provistos (ramas)', async () => {
    vi.mocked(postForm).mockResolvedValueOnce({ id_documento: 'd2' });
    const archivo = new File(['x'], 'doc.txt', { type: 'text/plain' });
    await documentosService.subir({ empresaId: 'e1', archivo });
    const fd = vi.mocked(postForm).mock.calls[0][1] as FormData;
    expect(fd.get('empresa_id')).toBe('e1');
    expect((fd.get('archivo') as File).name).toBe('doc.txt');
    expect(fd.get('carpeta_id')).toBeNull();
    expect(fd.get('descripcion')).toBeNull();
    expect(fd.get('carpeta_nombre')).toBeNull();
  });

  it('propaga el error si la subida falla', async () => {
    vi.mocked(postForm).mockRejectedValueOnce(new Error('413'));
    const archivo = new File(['x'], 'big.bin');
    await expect(documentosService.subir({ empresaId: 'e1', archivo })).rejects.toThrow('413');
  });
});

describe('documentosService.obtenerUrlDescarga / descargar', () => {
  it('obtenerUrlDescarga pide el JSON pre-firmado', async () => {
    vi.mocked(fetcher).mockResolvedValueOnce({
      url: 'https://s3/firmada',
      expires_in: 3600,
      nombre_archivo: 'factura.pdf',
    });
    const r = await documentosService.obtenerUrlDescarga('d1');
    expect(fetcher).toHaveBeenCalledWith('/gestion-documental/documentos/d1/descargar/');
    expect(r.url).toBe('https://s3/firmada');
  });

  it('descargar dispara el guardado en el navegador', async () => {
    vi.mocked(fetcher).mockResolvedValueOnce({
      url: 'https://s3/firmada',
      expires_in: 3600,
      nombre_archivo: 'factura.pdf',
    });
    const click = vi.fn();
    const anchor = { href: '', download: '', rel: '', click } as unknown as HTMLAnchorElement;
    const createEl = vi.spyOn(document, 'createElement').mockReturnValueOnce(anchor);
    const append = vi.spyOn(document.body, 'appendChild').mockImplementationOnce((n) => n);
    const remove = vi.spyOn(document.body, 'removeChild').mockImplementationOnce((n) => n);

    const r = await documentosService.descargar('d1');

    expect(anchor.href).toBe('https://s3/firmada');
    expect(anchor.download).toBe('factura.pdf');
    expect(click).toHaveBeenCalled();
    expect(r.nombre_archivo).toBe('factura.pdf');

    createEl.mockRestore();
    append.mockRestore();
    remove.mockRestore();
  });

  it('descargar propaga el error si falla obtener la URL', async () => {
    vi.mocked(fetcher).mockRejectedValueOnce(new Error('404'));
    await expect(documentosService.descargar('d1')).rejects.toThrow('404');
  });
});

describe('documentosService eliminar/actualizar', () => {
  it('eliminarArchivo pega al endpoint eliminar-archivo', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await documentosService.eliminarArchivo('d1');
    expect(del).toHaveBeenCalledWith('/gestion-documental/documentos/d1/eliminar-archivo/');
  });

  it('update envía PATCH con metadatos', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id_documento: 'd1' });
    await documentosService.update('d1', { descripcion: 'Nueva', id_carpeta: 'c2' });
    expect(patch).toHaveBeenCalledWith('/gestion-documental/documentos/d1/', {
      descripcion: 'Nueva',
      id_carpeta: 'c2',
    });
  });

  it('remove pega al DELETE base', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await documentosService.remove('d1');
    expect(del).toHaveBeenCalledWith('/gestion-documental/documentos/d1/');
  });
});

// ── Vínculos ──────────────────────────────────────────────────────────────────

describe('vinculosDocumentoService', () => {
  it('getAll filtra por documento en cliente y arma el query', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_vinculo: 'v1', id_documento: 'd1' },
      { id_vinculo: 'v2', id_documento: 'd2' },
    ]);
    const r = await vinculosDocumentoService.getAll({ documento: 'd1' });
    expect(get).toHaveBeenCalledWith('/gestion-documental/vinculos-documento/?id_documento=d1');
    expect(r).toEqual([{ id_vinculo: 'v1', id_documento: 'd1' }]);
  });

  it('getAll sin documento devuelve toda la lista', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_vinculo: 'v1', id_documento: 'd1' }] });
    const r = await vinculosDocumentoService.getAll();
    expect(get).toHaveBeenCalledWith('/gestion-documental/vinculos-documento/');
    expect(r.length).toBe(1);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_vinculo: 'v1' });
    await vinculosDocumentoService.getById('v1');
    expect(get).toHaveBeenCalledWith('/gestion-documental/vinculos-documento/v1/');
  });

  it('create envía el payload', async () => {
    const payload: VinculoDocumentoPayload = {
      id_documento: 'd1',
      id_entidad_origen: 'g1',
      nombre_modelo_origen: 'gastos.Gasto',
      tipo_vinculo: 'RESPALDO',
    };
    vi.mocked(post).mockResolvedValueOnce({ id_vinculo: 'v1' });
    await vinculosDocumentoService.create(payload);
    expect(post).toHaveBeenCalledWith('/gestion-documental/vinculos-documento/', payload);
  });

  it('update envía PATCH', async () => {
    const payload: VinculoDocumentoPayload = {
      id_documento: 'd1',
      id_entidad_origen: 'g1',
      nombre_modelo_origen: 'gastos.Gasto',
      tipo_vinculo: null,
    };
    vi.mocked(patch).mockResolvedValueOnce({ id_vinculo: 'v1' });
    await vinculosDocumentoService.update('v1', payload);
    expect(patch).toHaveBeenCalledWith('/gestion-documental/vinculos-documento/v1/', payload);
  });

  it('remove pega al DELETE', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await vinculosDocumentoService.remove('v1');
    expect(del).toHaveBeenCalledWith('/gestion-documental/vinculos-documento/v1/');
  });
});

// ── Permisos ──────────────────────────────────────────────────────────────────

describe('permisosDocumentoService', () => {
  it('getAll filtra por documento y arma el query', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_permiso_documento: 'pm1', id_documento: 'd1' },
      { id_permiso_documento: 'pm2', id_documento: 'd2' },
    ]);
    const r = await permisosDocumentoService.getAll({ documento: 'd1' });
    expect(get).toHaveBeenCalledWith('/gestion-documental/permisos-documento/?id_documento=d1');
    expect(r).toEqual([{ id_permiso_documento: 'pm1', id_documento: 'd1' }]);
  });

  it('getAll sin documento devuelve toda la lista', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_permiso_documento: 'pm1', id_documento: 'd1' }]);
    const r = await permisosDocumentoService.getAll();
    expect(get).toHaveBeenCalledWith('/gestion-documental/permisos-documento/');
    expect(r.length).toBe(1);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_permiso_documento: 'pm1' });
    await permisosDocumentoService.getById('pm1');
    expect(get).toHaveBeenCalledWith('/gestion-documental/permisos-documento/pm1/');
  });

  it('create envía el payload', async () => {
    const payload: PermisoDocumentoPayload = {
      id_documento: 'd1',
      id_usuario: 'u1',
      id_rol: null,
      puede_ver: true,
      puede_editar: false,
      puede_eliminar: false,
    };
    vi.mocked(post).mockResolvedValueOnce({ id_permiso_documento: 'pm1' });
    await permisosDocumentoService.create(payload);
    expect(post).toHaveBeenCalledWith('/gestion-documental/permisos-documento/', payload);
  });

  it('update envía PATCH', async () => {
    const payload: PermisoDocumentoPayload = {
      id_documento: 'd1',
      id_usuario: null,
      id_rol: 'r1',
      puede_ver: true,
      puede_editar: true,
      puede_eliminar: true,
    };
    vi.mocked(patch).mockResolvedValueOnce({ id_permiso_documento: 'pm1' });
    await permisosDocumentoService.update('pm1', payload);
    expect(patch).toHaveBeenCalledWith('/gestion-documental/permisos-documento/pm1/', payload);
  });

  it('remove pega al DELETE', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await permisosDocumentoService.remove('pm1');
    expect(del).toHaveBeenCalledWith('/gestion-documental/permisos-documento/pm1/');
  });
});
