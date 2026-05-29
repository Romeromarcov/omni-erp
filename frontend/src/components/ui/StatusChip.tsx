import { Chip } from '@mui/material';

type ChipColor = 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'info';

const ESTADO_COLOR: Record<string, ChipColor> = {
  // genéricos
  activo: 'success', inactivo: 'default', si: 'success', no: 'default',
  // ventas / documentos
  pendiente: 'warning', aprobado: 'success', anulado: 'error', rechazado: 'error',
  borrador: 'default', emitido: 'success', convertido: 'info', cerrado: 'default',
  // cobranza
  vigente: 'success', cumplido: 'info', roto: 'error', cancelado: 'warning',
  pagado: 'success', parcial: 'warning', vencido: 'error', vencida: 'error',
};

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
  const color = colorMap?.[key] ?? ESTADO_COLOR[key] ?? 'default';
  return <Chip size="small" label={label ?? text} color={color} variant={color === 'default' ? 'outlined' : 'filled'} />;
}
