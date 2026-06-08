// Servicio del Panel SaaS del proveedor (Plan C).
// Consume /api/saas/* — planes y suscripciones. La ESCRITURA de planes está
// restringida en backend a es_superusuario_omni; la UI que lo usa vive bajo
// la ruta protegida /admin-saas (guard de rol en saasRoutes.tsx).
import { get, post, patch, fetchText } from './api';

// ── Choices (espejo de apps/saas/models.py) ──────────────────────────────────
export type PlanNivel = 'FREE' | 'STARTER' | 'PRO' | 'ENTERPRISE';
export type PlanSoporte = 'email' | 'chat' | 'telefono' | 'dedicado';
export type SuscripcionEstado = 'ACTIVA' | 'VENCIDA' | 'CANCELADA' | 'SUSPENDIDA' | 'TRIAL';
export type SuscripcionPeriodo = 'MENSUAL' | 'ANUAL';

export const PLAN_NIVELES: PlanNivel[] = ['FREE', 'STARTER', 'PRO', 'ENTERPRISE'];
export const PLAN_SOPORTES: PlanSoporte[] = ['email', 'chat', 'telefono', 'dedicado'];
export const SUSCRIPCION_ESTADOS: SuscripcionEstado[] = [
  'ACTIVA', 'TRIAL', 'SUSPENDIDA', 'VENCIDA', 'CANCELADA',
];
export const SUSCRIPCION_PERIODOS: SuscripcionPeriodo[] = ['MENSUAL', 'ANUAL'];

// ── Tipos ─────────────────────────────────────────────────────────────────────
// Los DecimalField de DRF se serializan como string; se conservan como string
// para no perder precisión (R-CODE-4) y se parsean solo para visualizar.
export interface Plan {
  id_plan: string;
  nombre: string;
  nivel: PlanNivel;
  descripcion: string;
  precio_mensual: string;
  precio_anual: string;
  max_usuarios: number;
  max_empresas: number;
  max_documentos_mes: number;
  permite_ia: boolean;
  permite_api: boolean;
  permite_reportes_avanzados: boolean;
  permite_multimoneda: boolean;
  soporte: PlanSoporte;
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export type PlanPayload = Omit<Plan, 'id_plan' | 'fecha_creacion' | 'fecha_actualizacion'>;

export interface Suscripcion {
  id_suscripcion: string;
  id_empresa: string;
  id_plan: string;
  estado: SuscripcionEstado;
  periodo: SuscripcionPeriodo;
  fecha_inicio: string;
  fecha_fin: string;
  fecha_cancelacion: string | null;
  fecha_suspension: string | null;
  renovacion_automatica: boolean;
  monto_pagado: string;
  referencia_pago: string;
  notas: string;
  fecha_creacion: string;
  fecha_actualizacion: string;
  // Campos calculados (read-only) que añade el serializer.
  esta_vigente: boolean;
  dias_restantes: number;
  plan_nombre: string;
  plan_nivel: PlanNivel;
}

export interface SuscripcionPayload {
  id_empresa: string;
  id_plan: string;
  estado: SuscripcionEstado;
  periodo: SuscripcionPeriodo;
  fecha_inicio: string;
  fecha_fin: string;
  renovacion_automatica: boolean;
  monto_pagado: string;
  referencia_pago?: string;
  notas?: string;
}

// La API puede responder con o sin paginación según configuración del viewset.
type Paginated<T> = { results: T[]; count: number };
function toList<T>(data: T[] | Paginated<T>): T[] {
  return Array.isArray(data) ? data : (data?.results ?? []);
}

// ── Planes ─────────────────────────────────────────────────────────────────────
export async function fetchPlanes(incluirInactivos = false): Promise<Plan[]> {
  const query = incluirInactivos ? '?incluir_inactivos=true' : '';
  return toList(await get<Plan[] | Paginated<Plan>>(`/saas/planes/${query}`));
}

export async function fetchPlan(idPlan: string): Promise<Plan> {
  return get<Plan>(`/saas/planes/${idPlan}/`);
}

export async function createPlan(data: PlanPayload): Promise<Plan> {
  return post<Plan>('/saas/planes/', data as unknown as Record<string, unknown>);
}

export async function updatePlan(idPlan: string, data: Partial<PlanPayload>): Promise<Plan> {
  return patch<Plan>(`/saas/planes/${idPlan}/`, data as Record<string, unknown>);
}

/**
 * Soft-delete: el backend marca activo=False (no borra físicamente) y responde
 * 204 sin cuerpo. Se usa fetchText (no del) porque del → res.json() fallaría al
 * parsear un cuerpo vacío.
 */
export async function deactivatePlan(idPlan: string): Promise<void> {
  await fetchText(`/saas/planes/${idPlan}/`, { method: 'DELETE' });
}

// ── Suscripciones ────────────────────────────────────────────────────────────
export interface SuscripcionFiltro {
  estado?: SuscripcionEstado;
  empresa?: string;
}

export async function fetchSuscripciones(filtro: SuscripcionFiltro = {}): Promise<Suscripcion[]> {
  const params = new URLSearchParams();
  if (filtro.estado) params.set('estado', filtro.estado);
  if (filtro.empresa) params.set('empresa', filtro.empresa);
  const query = params.toString() ? `?${params.toString()}` : '';
  return toList(await get<Suscripcion[] | Paginated<Suscripcion>>(`/saas/suscripciones/${query}`));
}

export async function fetchSuscripcion(idSuscripcion: string): Promise<Suscripcion> {
  return get<Suscripcion>(`/saas/suscripciones/${idSuscripcion}/`);
}

export async function createSuscripcion(data: SuscripcionPayload): Promise<Suscripcion> {
  return post<Suscripcion>('/saas/suscripciones/', data as unknown as Record<string, unknown>);
}

export async function updateSuscripcion(
  idSuscripcion: string,
  data: Partial<SuscripcionPayload>,
): Promise<Suscripcion> {
  return patch<Suscripcion>(`/saas/suscripciones/${idSuscripcion}/`, data as Record<string, unknown>);
}

/** Reactiva una suscripción suspendida/vencida volviéndola a ACTIVA (PATCH estado). */
export async function activarSuscripcion(idSuscripcion: string): Promise<Suscripcion> {
  return patch<Suscripcion>(`/saas/suscripciones/${idSuscripcion}/`, { estado: 'ACTIVA' });
}

export async function suspenderSuscripcion(idSuscripcion: string): Promise<Suscripcion> {
  return post<Suscripcion>(`/saas/suscripciones/${idSuscripcion}/suspender/`, {});
}

export async function cancelarSuscripcion(idSuscripcion: string, notas = ''): Promise<Suscripcion> {
  return post<Suscripcion>(`/saas/suscripciones/${idSuscripcion}/cancelar/`, { notas });
}

// ── Auto-registro (signup, público — Fase C3) ────────────────────────────────
export interface SignupPayload {
  empresa_nombre_legal: string;
  empresa_nombre_comercial?: string;
  empresa_identificador_fiscal?: string;
  empresa_email?: string;
  username: string;
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
  plan_nivel?: PlanNivel;
}

export interface SignupResult {
  empresa_id: string;
  usuario_id: string;
  username: string;
  suscripcion_id: string;
  plan: string;
  estado: SuscripcionEstado;
  trial_fin: string;
}

/** Endpoint PÚBLICO: crea empresa + admin + suscripción TRIAL. No requiere auth. */
export async function signup(payload: SignupPayload): Promise<SignupResult> {
  return post<SignupResult>('/saas/signup/', payload as unknown as Record<string, unknown>);
}

// ── Métricas del dashboard (cálculo en cliente) ──────────────────────────────
const ESTADOS_VIGENTES: SuscripcionEstado[] = ['ACTIVA', 'TRIAL'];

/**
 * MRR estimado: suma del valor mensualizado de las suscripciones vigentes.
 * Para periodo ANUAL se mensualiza dividiendo el precio anual entre 12.
 * Usa los precios del plan asociado (join por id_plan).
 */
export function estimarMrr(suscripciones: Suscripcion[], planes: Plan[]): number {
  const planPorId = new Map(planes.map((p) => [p.id_plan, p]));
  let mrr = 0;
  for (const s of suscripciones) {
    if (!ESTADOS_VIGENTES.includes(s.estado)) continue;
    const plan = planPorId.get(s.id_plan);
    if (!plan) continue;
    if (s.periodo === 'ANUAL') {
      mrr += (Number(plan.precio_anual) || 0) / 12;
    } else {
      mrr += Number(plan.precio_mensual) || 0;
    }
  }
  return mrr;
}
