import { Chip } from '@mui/material';

type ChipColor = 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'info';

// La clave viene de datos del backend; Map evita que valores como "__proto__"
// alcancen la cadena de prototipos de un objeto plano (CTF-006).
const ESTADO_COLOR_DEF: Record<string, ChipColor> = {
  // genéricos
  activo: 'success', inactivo: 'default', si: 'success', no: 'default',
  // ventas / documentos
  pendiente: 'warning', aprobado: 'success', anulado: 'error', rechazado: 'error',
  borrador: 'default', emitido: 'success', convertido: 'info', cerrado: 'default',
  // cobranza
  vigente: 'success', cumplido: 'info', roto: 'error', cancelado: 'warning',
  pagado: 'success', parcial: 'warning', vencido: 'error', vencida: 'error',
};
const ESTADO_COLOR = new Map(Object.entries(ESTADO_COLOR_DEF));

interface StatusChipProps {
  value: string | boolean | null | undefined;
  /** Mapa opcional para sobreescribir colores por valor (en minúsculas). */
  colorMap?: Record<string, ChipColor>;
  label?: string;
}

export default function StatusChip({ value, colorMap, label }: StatusChipProps) {
  const text =
    typeof value === 'boolean' ? (value ? 'Sí' : 'No') : (value ?? '—').toString();
  const key = text.toLowerCase().trim();
  const colorPropio =
    // eslint-disable-next-line security/detect-object-injection -- FP: lectura limitada a propiedades propias por el Object.hasOwn de esta misma expresión
    colorMap && Object.hasOwn(colorMap, key) ? colorMap[key] : undefined;
  const color = colorPropio ?? ESTADO_COLOR.get(key) ?? 'default';
  return <Chip size="small" label={label ?? text} color={color} variant={color === 'default' ? 'outlined' : 'filled'} />;
}
