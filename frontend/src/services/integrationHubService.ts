/**
 * Integration Hub Service
 * Funciones para interactuar con la API del módulo de integraciones.
 */
import { get, post } from './api';

// ── Tipos ────────────────────────────────────────────────────────────────────

export interface ConectorProveedor {
  id_proveedor: string;
  codigo: string;
  nombre: string;
  descripcion: string;
  icono_url: string;
  capacidades: string[];
  requiere_db?: boolean;
  estado: 'activo' | 'beta' | 'proximamente';
  versiones_soportadas: string[];
}

export interface ConectorInstancia {
  id_conector: string;
  id_empresa: string;
  id_proveedor: string;
  proveedor_nombre: string;
  proveedor_codigo: string;
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

export interface ConectorInstanciaCreate {
  id_proveedor: string;
  nombre: string;
  entidades_activas?: string[];
  intervalo_sync_minutos?: number;
  configuracion: {
    host: string;
    db?: string;
    user: string;
    api_key: string;
    timeout?: number;
  };
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

export interface IntegrationHubStatus {
  conectores_activos: number;
  conectores_total: number;
  ultima_24h: {
    total: number;
    completados: number;
    con_errores: number;
    fallidos: number;
    en_progreso: number;
  };
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ── Proveedores ──────────────────────────────────────────────────────────────

export async function getProveedores(): Promise<PaginatedResponse<ConectorProveedor>> {
  return get<PaginatedResponse<ConectorProveedor>>('/integration-hub/proveedores/');
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
