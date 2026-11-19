/**
 * GAP-11: Zod validation schemas for fiscal configuration forms.
 */
import { z } from 'zod';
import { parseDecimalSeguro } from './decimal.schemas';

// ── Configuración Fiscal ──────────────────────────────────────────────────────

export const configuracionFiscalSchema = z.object({
  contribuyente_iva: z.boolean(),
  aplica_igtf: z.boolean(),
  tasa_igtf: z
    .string()
    .optional()
    .refine(
      (v) => {
        if (!v) return true;
        const d = parseDecimalSeguro(v);
        return d !== null && d.gte(0) && d.lte(1);
      },
      { message: 'La tasa IGTF debe estar entre 0.0000 y 1.0000 (ej: 0.03 para 3%)' }
    ),
});

export type ConfiguracionFiscalInput = z.infer<typeof configuracionFiscalSchema>;

// ── Tasa IVA ──────────────────────────────────────────────────────────────────

const tipoTasaIVA = ['GENERAL', 'REDUCIDO', 'ADICIONAL', 'EXENTO'] as const;

export const tasaIVASchema = z.object({
  nombre: z.string().min(2, 'El nombre debe tener al menos 2 caracteres').max(100),
  tipo: z.enum(tipoTasaIVA, {
    error: () => 'El tipo de tasa no es válido',
  }),
  tasa: z
    .string()
    .min(1, 'La tasa es obligatoria')
    .refine(
      (v) => {
        const d = parseDecimalSeguro(v);
        return d !== null && d.gte(0) && d.lte(1);
      },
      { message: 'La tasa debe estar entre 0.0000 y 1.0000 (ej: 0.16 para 16%)' }
    ),
  activo: z.boolean().default(true),
});

export type TasaIVAInput = z.infer<typeof tasaIVASchema>;

// ── Periodo fiscal ────────────────────────────────────────────────────────────

export const periodoFiscalSchema = z.object({
  periodo: z
    .string()
    .regex(/^\d{4}-(0[1-9]|1[0-2])$/, 'El período debe tener formato YYYY-MM (ej: 2026-05)'),
});

export type PeriodoFiscalInput = z.infer<typeof periodoFiscalSchema>;
