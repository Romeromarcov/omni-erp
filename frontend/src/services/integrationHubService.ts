/**
 * Integration Hub Service
 * Funciones para interactuar con la API del módulo de integraciones.
 */
import { get, post, patch, fetchText } from './api';

// ── Tipos ────────────────────────────────────────────────────────────────────

export type ProveedorEstado = 'activo' | 'beta' | 'proximamente';

export interface ConectorProveedor {
  id_proveedor: string;
  codigo: string;
  nombre: string;
  descripcion: string;
  icono_url: string;
  capacidades: string[];
  requiere_url?: boolean;
  requiere_db?: boolean;
  estado: ProveedorEstado;
  versiones_soportadas: string[];
  activo?: boolean;
  orden?: number;
}

/** Payload de alta/edición de un proveedor (Panel SaaS, solo superusuario Omni). */
export type ConectorProveedorPayload = Omit<ConectorProveedor, 'id_proveedor'>;

export interface ConectorInstancia {
  id_conector: string;
  id_empresa: string;
  id_proveedor: string;
  proveedor_nombre: string;
  proveedor_codigo: string;
  proveedor_capacidades: string[];
  nombre: string;
  estado: 'configurando' | 'activo' | 'error' | 'inactivo';
  intervalo_sync_minutos: number;
  entidades_activas: string[];
  version_detectada: string;
  configuracion_publica: {
    host?: string;
    db?: string;
    user?: string;
    timeout?: number;
  };
  ultimo_sync: string | null;
  creado_en: string;
}

/** Configuración de un conector tipo Odoo / fuente de datos vía API. */
export interface ConectorConfiguracionApi {
  host: string;
  db?: string;
  user: string;
  api_key: string;
  timeout?: number;
}

/**
 * Configuración del conector Google Sheets (destino/outbound).
 * `service_account` es el JSON de la cuenta de servicio — SECRETO: nunca se
 * vuelve a leer ni se muestra tras guardarlo (R-CODE-8).
 */
export interface ConectorConfiguracionSheets {
  service_account: Record<string, unknown>;
  source_instancia_id: string;
  drive_folder_id?: string;
  spreadsheet_id?: string;
  titulo?: string;
}

export interface ConectorInstanciaCreate {
  id_proveedor: string;
  nombre: string;
  entidades_activas?: string[];
  intervalo_sync_minutos?: number;
  configuracion: ConectorConfiguracionApi | ConectorConfiguracionSheets;
}

/**
 * Payload de edición de un conector. Todos los campos son opcionales (PATCH).
 * En `configuracion`, los secretos (api_key/service_account) que lleguen vacíos
 * NO se sobreescriben: el backend conserva el valor cifrado existente.
 */
export interface ConectorInstanciaUpdate {
  nombre?: string;
  entidades_activas?: string[];
  intervalo_sync_minutos?: number;
  activo?: boolean;
  configuracion?: Partial<ConectorConfiguracionApi> | Partial<ConectorConfiguracionSheets>;
}

export interface JobSincronizacion {
  id_job: string;
  id_instancia: string;
  tipo_entidad: string;
  direccion: string;
  estado: 'pendiente' | 'en_progreso' | 'completado' | 'completado_con_errores' | 'fallido';
  total_registros: number;
  procesados: number;
  creados: number;
  actualizados: number;
  omitidos: number;
  fallidos: number;
  iniciado_en: string;
  completado_en: string | null;
  duracion_segundos: number | null;
}

export interface TestConnectionResult {
  success: boolean;
  message: string;
  version?: string;
}

export interface TriggerSyncResult {
  success: boolean;
  job_id?: string;
  mensaje?: string;
  error?: string;
}

/** Respuesta 202 del endpoint de exportación a Google Sheets. */
export interface TriggerExportResult {
  mensaje: string;
  task_id: string;
}

export interface IntegrationHubStatus {
  // Forma real del backend (IntegrationHubStatusView): el contrato anterior
  // (conectores_activos/ultima_24h) nunca existió y rompía la página.
  conectores: {
    total: number;
    activos: number;
    con_error: number;
    configurando: number;
    inactivos: number;
  };
  jobs_24h: {
    total: number;
    completados: number;
    con_errores: number;
    fallidos: number;
    en_progreso: number;
  };
  proveedores_disponibles: string[];
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ── Proveedores ──────────────────────────────────────────────────────────────

export async function getProveedores(): Promise<ConectorProveedor[]> {
  // El endpoint tiene pagination_class = None → responde una lista plana, no un
  // objeto paginado {results}. Toleramos ambas formas por robustez (si algún día
  // se le activa paginación, no se rompe el selector de proveedores del modal).
  const data = await get<ConectorProveedor[] | PaginatedResponse<ConectorProveedor>>(
    '/integration-hub/proveedores/',
  );
  return Array.isArray(data) ? data : (data?.results ?? []);
}

// ── Gestión del catálogo (Panel SaaS — solo superusuario Omni) ─────────────────
// La escritura está restringida en backend a es_superusuario_omni; la UI vive
// bajo la ruta protegida /admin-saas.

/** Lista proveedores; con `incluirInactivos` trae también los desactivados. */
export async function getProveedoresAdmin(
  incluirInactivos = false,
): Promise<ConectorProveedor[]> {
  const query = incluirInactivos ? '?incluir_inactivos=true' : '';
  const data = await get<ConectorProveedor[] | PaginatedResponse<ConectorProveedor>>(
    `/integration-hub/proveedores/${query}`,
  );
  return Array.isArray(data) ? data : (data?.results ?? []);
}

export async function getProveedor(id: string): Promise<ConectorProveedor> {
  return get<ConectorProveedor>(`/integration-hub/proveedores/${id}/`);
}

export async function createProveedor(
  data: ConectorProveedorPayload,
): Promise<ConectorProveedor> {
  return post<ConectorProveedor>(
    '/integration-hub/proveedores/',
    data as unknown as Record<string, unknown>,
  );
}

export async function updateProveedor(
  id: string,
  data: Partial<ConectorProveedorPayload>,
): Promise<ConectorProveedor> {
  return patch<ConectorProveedor>(
    `/integration-hub/proveedores/${id}/`,
    data as Record<string, unknown>,
  );
}

/** Borrado lógico: el backend marca `activo=False` y responde 204 sin cuerpo. */
export async function deactivateProveedor(id: string): Promise<void> {
  await fetchText(`/integration-hub/proveedores/${id}/`, { method: 'DELETE' });
}

// ── Instancias ───────────────────────────────────────────────────────────────

export async function getConectores(): Promise<PaginatedResponse<ConectorInstancia>> {
  return get<PaginatedResponse<ConectorInstancia>>('/integration-hub/instancias/');
}

export async function getConector(id: string): Promise<ConectorInstancia> {
  return get<ConectorInstancia>(`/integration-hub/instancias/${id}/`);
}

export async function crearConector(data: ConectorInstanciaCreate): Promise<ConectorInstancia> {
  return post<ConectorInstancia>('/integration-hub/instancias/', data as unknown as Record<string, unknown>);
}

export async function actualizarConector(
  id: string,
  data: ConectorInstanciaUpdate,
): Promise<ConectorInstancia> {
  return patch<ConectorInstancia>(
    `/integration-hub/instancias/${id}/`,
    data as unknown as Record<string, unknown>,
  );
}

export async function testConector(id: string): Promise<TestConnectionResult> {
  return post<TestConnectionResult>(`/integration-hub/instancias/${id}/test/`, {});
}

export async function triggerSync(
  id: string,
  tipoEntidad: string,
): Promise<TriggerSyncResult> {
  return post<TriggerSyncResult>(`/integration-hub/instancias/${id}/sync/`, {
    tipo_entidad: tipoEntidad,
  });
}

/**
 * Dispara una exportación outbound (p. ej. a Google Sheets). Responde 202 con un
 * `task_id`; el avance se sigue puleando `getJobsDeConector` (jobs `outbound`).
 *
 * @param tipos  entidades a exportar; `null`/omitido = todas las activas.
 * @param full   `true` para reexportar todo el histórico, no solo lo nuevo.
 */
export async function exportarConector(
  id: string,
  opts: { tipos?: string[] | null; full?: boolean } = {},
): Promise<TriggerExportResult> {
  const body: Record<string, unknown> = {};
  if (opts.tipos != null) body.tipos = opts.tipos;
  if (opts.full != null) body.full = opts.full;
  return post<TriggerExportResult>(`/integration-hub/instancias/${id}/exportar/`, body);
}

export async function getJobsDeConector(id: string): Promise<PaginatedResponse<JobSincronizacion>> {
  return get<PaginatedResponse<JobSincronizacion>>(`/integration-hub/instancias/${id}/jobs/`);
}

// ── Jobs globales ────────────────────────────────────────────────────────────

export async function getJobs(params?: {
  instancia?: string;
  estado?: string;
  tipo_entidad?: string;
}): Promise<PaginatedResponse<JobSincronizacion>> {
  const qs = params
    ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => !!v) as [string, string][]).toString()
    : '';
  return get<PaginatedResponse<JobSincronizacion>>(`/integration-hub/jobs/${qs}`);
}

// ── Estado general ───────────────────────────────────────────────────────────

export async function getIntegrationHubStatus(): Promise<IntegrationHubStatus> {
  return get<IntegrationHubStatus>('/integration-hub/status/');
}
