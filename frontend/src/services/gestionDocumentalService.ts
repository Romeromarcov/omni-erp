import { get, post, patch, del, postForm, fetcher } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos ─────────────────────────────────────────────────────────────────────

/** Carpeta jerárquica de documentos (puede tener carpeta padre). */
export interface Carpeta {
  id_carpeta: string;
  id_empresa: string;
  nombre_carpeta: string;
  fecha_creacion?: string;
  es_publica?: boolean;
  activo?: boolean;
  id_carpeta_padre?: string | null;
  id_usuario_creacion?: string;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface CarpetaPayload {
  id_empresa: string;
  nombre_carpeta: string;
  id_carpeta_padre: string | null;
  es_publica: boolean;
  activo: boolean;
  id_usuario_creacion: string;
}

/** Documento con archivo adjunto en S3/MinIO. */
export interface Documento {
  id_documento: string;
  id_empresa: string;
  nombre_archivo: string;
  tipo_contenido: string;
  tamano_bytes: number;
  ruta_almacenamiento: string;
  fecha_subida?: string;
  descripcion?: string | null;
  activo?: boolean;
  version?: number;
  id_usuario_subida?: string;
  id_carpeta?: string | null;
}

/** Metadatos de subida multipart (el archivo va aparte como File). */
export interface SubirDocumentoParams {
  empresaId: string;
  archivo: File;
  carpetaId?: string | null;
  descripcion?: string;
  /** Subcarpeta lógica en S3 (default 'general'). */
  carpetaNombre?: string;
}

/** Respuesta de la acción descargar (URL pre-firmada temporal). */
export interface DescargaDocumento {
  url: string;
  expires_in: number;
  nombre_archivo: string;
}

/** Vínculo de un documento a otra entidad del sistema. */
export interface VinculoDocumento {
  id_vinculo: string;
  id_documento: string;
  id_entidad_origen: string;
  nombre_modelo_origen: string;
  tipo_vinculo?: string | null;
  fecha_vinculo?: string;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface VinculoDocumentoPayload {
  id_documento: string;
  id_entidad_origen: string;
  nombre_modelo_origen: string;
  tipo_vinculo: string | null;
}

/** Permiso (usuario o rol) sobre un documento. */
export interface PermisoDocumento {
  id_permiso_documento: string;
  id_documento: string;
  id_usuario?: string | null;
  id_rol?: string | null;
  puede_ver?: boolean;
  puede_editar?: boolean;
  puede_eliminar?: boolean;
  fecha_asignacion?: string;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface PermisoDocumentoPayload {
  id_documento: string;
  id_usuario: string | null;
  id_rol: string | null;
  puede_ver: boolean;
  puede_editar: boolean;
  puede_eliminar: boolean;
}

const BASE = '/gestion-documental';

// ── Carpetas (CRUD jerárquico) ────────────────────────────────────────────────

export const carpetasService = {
  getAll: async (params?: { empresa?: string; padre?: string; search?: string }): Promise<Carpeta[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('id_empresa', params.empresa);
    if (params?.padre) qs.set('id_carpeta_padre', params.padre);
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString();
    const response = await get<PaginatedResponse<Carpeta> | Carpeta[]>(
      `${BASE}/carpetas/${query ? '?' + query : ''}`,
    );
    return toList<Carpeta>(response);
  },

  getById: async (id: string): Promise<Carpeta> => get<Carpeta>(`${BASE}/carpetas/${id}/`),

  create: async (payload: CarpetaPayload): Promise<Carpeta> =>
    post<Carpeta>(`${BASE}/carpetas/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: CarpetaPayload): Promise<Carpeta> =>
    patch<Carpeta>(`${BASE}/carpetas/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/carpetas/${id}/`);
  },
};

// ── Documentos (CRUD + subir multipart + descargar + eliminar archivo) ────────

export const documentosService = {
  getAll: async (params?: {
    empresa?: string;
    carpeta?: string;
    search?: string;
  }): Promise<Documento[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('id_empresa', params.empresa);
    if (params?.carpeta) qs.set('id_carpeta', params.carpeta);
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString();
    const response = await get<PaginatedResponse<Documento> | Documento[]>(
      `${BASE}/documentos/${query ? '?' + query : ''}`,
    );
    return toList<Documento>(response);
  },

  getById: async (id: string): Promise<Documento> => get<Documento>(`${BASE}/documentos/${id}/`),

  /**
   * Sube un archivo + metadatos vía multipart/form-data. El backend espera el
   * binario en el campo `archivo` y `empresa_id`; `carpeta_id`, `descripcion` y
   * `carpeta_nombre` son opcionales. `postForm` NO fija Content-Type (el browser
   * agrega el boundary correcto al serializar el FormData).
   */
  subir: async (params: SubirDocumentoParams): Promise<Documento> => {
    const form = new FormData();
    form.set('archivo', params.archivo);
    form.set('empresa_id', params.empresaId);
    if (params.carpetaId) form.set('carpeta_id', params.carpetaId);
    if (params.descripcion) form.set('descripcion', params.descripcion);
    if (params.carpetaNombre) form.set('carpeta_nombre', params.carpetaNombre);
    return postForm<Documento>(`${BASE}/documentos/subir/`, form);
  },

  /**
   * Obtiene la URL pre-firmada de descarga. El backend devuelve un JSON con
   * `url` temporal; el llamador puede abrirla o usar `descargar` para disparar
   * el guardado en el navegador.
   */
  obtenerUrlDescarga: async (id: string): Promise<DescargaDocumento> =>
    fetcher<DescargaDocumento>(`${BASE}/documentos/${id}/descargar/`),

  /**
   * Dispara la descarga del archivo: pide la URL pre-firmada y navega/clic sobre
   * un ancla con `download` para que el navegador guarde el archivo.
   */
  descargar: async (id: string): Promise<DescargaDocumento> => {
    const datos = await documentosService.obtenerUrlDescarga(id);
    const a = document.createElement('a');
    a.href = datos.url;
    a.download = datos.nombre_archivo;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    return datos;
  },

  /** Borrado lógico del documento/archivo (DELETE eliminar-archivo). */
  eliminarArchivo: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/documentos/${id}/eliminar-archivo/`);
  },

  /** Actualiza metadatos del documento (descripción, carpeta). */
  update: async (
    id: string,
    payload: { descripcion?: string | null; id_carpeta?: string | null },
  ): Promise<Documento> =>
    patch<Documento>(`${BASE}/documentos/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/documentos/${id}/`);
  },
};

// ── Vínculos de documento (CRUD) ──────────────────────────────────────────────

export const vinculosDocumentoService = {
  getAll: async (params?: { documento?: string }): Promise<VinculoDocumento[]> => {
    const qs = new URLSearchParams();
    if (params?.documento) qs.set('id_documento', params.documento);
    const query = qs.toString();
    const response = await get<PaginatedResponse<VinculoDocumento> | VinculoDocumento[]>(
      `${BASE}/vinculos-documento/${query ? '?' + query : ''}`,
    );
    const lista = toList<VinculoDocumento>(response);
    return params?.documento ? lista.filter((v) => v.id_documento === params.documento) : lista;
  },

  getById: async (id: string): Promise<VinculoDocumento> =>
    get<VinculoDocumento>(`${BASE}/vinculos-documento/${id}/`),

  create: async (payload: VinculoDocumentoPayload): Promise<VinculoDocumento> =>
    post<VinculoDocumento>(
      `${BASE}/vinculos-documento/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: VinculoDocumentoPayload): Promise<VinculoDocumento> =>
    patch<VinculoDocumento>(
      `${BASE}/vinculos-documento/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/vinculos-documento/${id}/`);
  },
};

// ── Permisos de documento (CRUD) ──────────────────────────────────────────────

export const permisosDocumentoService = {
  getAll: async (params?: { documento?: string }): Promise<PermisoDocumento[]> => {
    const qs = new URLSearchParams();
    if (params?.documento) qs.set('id_documento', params.documento);
    const query = qs.toString();
    const response = await get<PaginatedResponse<PermisoDocumento> | PermisoDocumento[]>(
      `${BASE}/permisos-documento/${query ? '?' + query : ''}`,
    );
    const lista = toList<PermisoDocumento>(response);
    return params?.documento ? lista.filter((p) => p.id_documento === params.documento) : lista;
  },

  getById: async (id: string): Promise<PermisoDocumento> =>
    get<PermisoDocumento>(`${BASE}/permisos-documento/${id}/`),

  create: async (payload: PermisoDocumentoPayload): Promise<PermisoDocumento> =>
    post<PermisoDocumento>(
      `${BASE}/permisos-documento/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: PermisoDocumentoPayload): Promise<PermisoDocumento> =>
    patch<PermisoDocumento>(
      `${BASE}/permisos-documento/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/permisos-documento/${id}/`);
  },
};
