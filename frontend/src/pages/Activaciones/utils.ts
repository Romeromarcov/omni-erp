import { mensajeDeError } from '../../utils/api';
import type { EventoActivacion } from '../../services/activacionesService';

/** `datetime-local` («2026-12-05T09:00») → ISO 8601 con zona del navegador; '' si es inválido. */
export function localAISO(valor: string): string {
  if (!valor) return '';
  const d = new Date(valor);
  return Number.isNaN(d.getTime()) ? '' : d.toISOString();
}

/** Texto legible de un evento en el calendario: «05/12/2026 09:00 – 13:00». */
export function formatearRango(inicio: string, fin: string): string {
  const i = new Date(inicio);
  const f = new Date(fin);
  const dia = i.toLocaleDateString('es-VE');
  const hora = (d: Date) => d.toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' });
  return `${dia} ${hora(i)} – ${hora(f)}`;
}

/** «Promotoras ×1 · Igloos ×2» (solo los recursos con cantidad > 0). */
export function textoUsos(e: Pick<EventoActivacion, 'usos'>): string {
  const partes = e.usos.filter((u) => u.cantidad > 0).map((u) => `${u.recurso_codigo} ×${u.cantidad}`);
  return partes.length ? partes.join(' · ') : '—';
}

/**
 * Mensaje de error de la API de activaciones. El backend responde 409 con
 * `{error, detalle}` cuando no cabe por capacidad: se muestra solo `error`
 * (texto en español); `detalle` es un objeto y no debe imprimirse crudo.
 */
export function mensajeActivacion(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) {
    try {
      const parsed: unknown = JSON.parse(err.message);
      if (parsed && typeof parsed === 'object' && 'error' in parsed) {
        const texto = (parsed as { error: unknown }).error;
        if (typeof texto === 'string' && texto) return texto;
      }
    } catch {
      /* no era JSON: se delega */
    }
  }
  return mensajeDeError(err, fallback);
}
