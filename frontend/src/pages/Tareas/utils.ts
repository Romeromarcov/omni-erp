import { mensajeDeError } from '../../utils/api';
import type {
  EstadoTarea,
  FrecuenciaRecurrente,
  ItemBorradorMinuta,
  PrioridadTarea,
  Tarea,
} from '../../services/tareasService';
import { PRIORIDADES_TAREA } from '../../services/tareasService';

export const ESTADO_TAREA_COLOR: Record<
  string,
  'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'
> = {
  pendiente: 'default',
  en_ejecucion: 'info',
  en_revision: 'secondary',
  bloqueada: 'error',
  completada: 'success',
  cancelada: 'default',
};

export const PRIORIDAD_TAREA_COLOR: Record<
  string,
  'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'
> = {
  baja: 'default',
  media: 'info',
  alta: 'warning',
  urgente: 'error',
};

export const ESTADO_MINUTA_COLOR: Record<string, 'default' | 'info' | 'success' | 'warning'> = {
  borrador: 'warning',
  confirmada: 'success',
  descartada: 'default',
};

const ESTADO_LABELS = new Map<string, string>([
  ['PENDIENTE', 'Pendiente'],
  ['EN_EJECUCION', 'En ejecución'],
  ['EN_REVISION', 'En revisión'],
  ['BLOQUEADA', 'Bloqueada'],
  ['COMPLETADA', 'Completada'],
  ['CANCELADA', 'Cancelada'],
]);

const PRIORIDAD_LABELS = new Map<string, string>([
  ['BAJA', 'Baja'],
  ['MEDIA', 'Media'],
  ['ALTA', 'Alta'],
  ['URGENTE', 'Urgente'],
]);

const FRECUENCIA_LABELS = new Map<string, string>([
  ['INTRADIA', 'Intradía (horaria)'],
  ['DIARIA', 'Diaria'],
  ['SEMANAL', 'Semanal'],
  ['QUINCENAL', 'Quincenal'],
  ['MENSUAL', 'Mensual'],
]);

const ORIGEN_LABELS = new Map<string, string>([
  ['WEB', 'Web'],
  ['BOT', 'Bot Telegram'],
  ['MINUTA_IA', 'Minuta IA'],
  ['RECURRENCIA', 'Recurrente'],
  ['AGENTE', 'Agente IA'],
  ['ERP_EVENTO', 'Evento ERP'],
]);

export const DIAS_SEMANA_OPCIONES: readonly { valor: number; etiqueta: string }[] = [
  { valor: 0, etiqueta: 'Lun' },
  { valor: 1, etiqueta: 'Mar' },
  { valor: 2, etiqueta: 'Mié' },
  { valor: 3, etiqueta: 'Jue' },
  { valor: 4, etiqueta: 'Vie' },
  { valor: 5, etiqueta: 'Sáb' },
  { valor: 6, etiqueta: 'Dom' },
] as const;

export function etiquetaEstadoTarea(estado: EstadoTarea | string): string {
  return ESTADO_LABELS.get(estado) ?? estado;
}

export function etiquetaPrioridadTarea(prioridad: PrioridadTarea | string): string {
  return PRIORIDAD_LABELS.get(prioridad) ?? prioridad;
}

export function etiquetaFrecuencia(frecuencia: FrecuenciaRecurrente | string): string {
  return FRECUENCIA_LABELS.get(frecuencia) ?? frecuencia;
}

export function etiquetaOrigenTarea(origen: string): string {
  return ORIGEN_LABELS.get(origen) ?? origen;
}

export function esTareaVencida(
  tarea: Pick<Tarea, 'estado' | 'fecha_vencimiento'>,
  hoyISO?: string,
): boolean {
  if (!tarea.fecha_vencimiento) return false;
  if (tarea.estado === 'COMPLETADA' || tarea.estado === 'CANCELADA') return false;
  const hoy = hoyISO ?? new Date().toISOString().slice(0, 10);
  return tarea.fecha_vencimiento < hoy;
}

/**
 * Convierte texto libre de acuerdos (una línea por acuerdo) en borradores para el
 * enriquecedor del backend. Soporta formato compacto:
 *   `Título | Responsable | Fecha (YYYY-MM-DD, hoy, mañana, viernes) | Prioridad`
 */
export function parsearLineasMinuta(textoLineas: string): ItemBorradorMinuta[] {
  const resultado: ItemBorradorMinuta[] = [];
  for (const lineaCruda of textoLineas.split(/\r?\n/)) {
    const limpia = lineaCruda.replace(/^[-*•\d.)\s]+/, '').trim();
    if (!limpia) continue;
    const partes = limpia.split('|').map((s) => s.trim());
    const titulo = partes.at(0) ?? '';
    if (!titulo) continue;
    const asignado = partes.at(1) ?? '';
    const fecha = partes.at(2) ?? '';
    const prioRaw = (partes.at(3) ?? '').toUpperCase();
    const prioridad: PrioridadTarea = (PRIORIDADES_TAREA as readonly string[]).includes(prioRaw)
      ? (prioRaw as PrioridadTarea)
      : 'MEDIA';

    const item: ItemBorradorMinuta = { titulo, prioridad };
    if (asignado) item.asignado_nombre = asignado;
    if (fecha) item.fecha_vencimiento = fecha;
    resultado.push(item);
  }
  return resultado;
}

function extraerHojasTexto(nodo: unknown, profundidad = 0): string[] {
  if (profundidad > 5 || nodo === null || nodo === undefined) return [];
  if (typeof nodo === 'string') return nodo.trim() ? [nodo.trim()] : [];
  if (typeof nodo === 'number' || typeof nodo === 'boolean') return [String(nodo)];
  if (Array.isArray(nodo)) {
    return nodo.flatMap((item) => extraerHojasTexto(item, profundidad + 1));
  }
  if (typeof nodo === 'object') {
    const salidas: string[] = [];
    for (const [clave, valor] of Object.entries(nodo)) {
      const hojas = extraerHojasTexto(valor, profundidad + 1);
      if (hojas.length === 0) continue;
      if (clave === 'error' || clave === 'detail' || clave === 'non_field_errors' || /^\d+$/.test(clave)) {
        salidas.push(...hojas);
      } else {
        salidas.push(`${clave}: ${hojas.join(', ')}`);
      }
    }
    return salidas;
  }
  return [];
}

/**
 * Extrae mensajes legibles en español desde respuestas JSON `{error}`, `{detail}` o
 * validaciones anidadas de DRF (`ListField`, `many=True`) sin exponer `[object Object]`.
 */
export function mensajeTareas(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) {
    try {
      const parsed: unknown = JSON.parse(err.message);
      const hojas = extraerHojasTexto(parsed);
      if (hojas.length > 0) return hojas.join(' · ');
    } catch {
      /* no era JSON serializado */
    }
  }
  return mensajeDeError(err, fallback);
}
