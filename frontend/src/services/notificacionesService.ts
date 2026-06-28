import { get, patch } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos ─────────────────────────────────────────────────────────────────────

/**
 * Notificación in-app del usuario. Espejo de `NotificacionSerializer`
 * (apps/notificaciones/serializers.py); todos los campos son read-only en el
 * backend. `url_accion` y `metadata` pueden venir vacíos.
 */
export interface Notificacion {
  id_notificacion: string;
  tipo: string;
  titulo: string;
  mensaje: string;
  leida: boolean;
  fecha_lectura: string | null;
  url_accion: string;
  metadata: Record<string, unknown> | null;
  fecha_creacion: string;
}

const BASE = '/notificaciones/notificaciones';

// ── Servicio ──────────────────────────────────────────────────────────────────

export const notificacionesService = {
  /**
   * Últimas 20 notificaciones del usuario autenticado. La action devuelve una
   * lista directa (no paginada), pero normalizamos con `toList` por robustez
   * (defensa ante cambios de backend: lista directa o `{results}`).
   */
  misNotificaciones: async (soloNoLeidas = false): Promise<Notificacion[]> => {
    const qs = soloNoLeidas ? '?no_leidas=true' : '';
    const response = await get<PaginatedResponse<Notificacion> | Notificacion[]>(
      `${BASE}/mis-notificaciones/${qs}`,
    );
    return toList<Notificacion>(response);
  },

  /** Marca una notificación como leída y devuelve su versión actualizada. */
  marcarLeida: async (id: string): Promise<Notificacion> =>
    patch<Notificacion>(`${BASE}/${id}/marcar-leida/`, {}),
};
