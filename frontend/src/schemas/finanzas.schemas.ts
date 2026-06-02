/**
 * FE-CRIT-1: Zod validation schemas for finanzas forms.
 * Used with react-hook-form + @hookform/resolvers/zod.
 */
import { z } from 'zod';

// ── Moneda ────────────────────────────────────────────────────────────────────

export const monedaSchema = z.object({
  tipo_moneda: z.enum(['fiat', 'crypto', 'otro'], {
    errorMap: () => ({ message: 'El tipo de moneda no es válido' }),
  }),
  codigo_iso: z
    .string()
    .min(2, 'El código ISO debe tener al menos 2 caracteres')
    .max(5, 'El código ISO no puede superar 5 caracteres'),
  nombre: z.string().min(2, 'El nombre debe tener al menos 2 caracteres').max(100),
  simbolo: z.string().min(1, 'El símbolo es obligatorio').max(10),
  decimales: z.coerce
    .number({ invalid_type_error: 'Los decimales deben ser un número' })
    .int('Los decimales deben ser un número entero')
    .min(0, 'Los decimales no pueden ser negativos')
    .max(8, 'Los decimales no pueden superar 8'),
  activo: z.boolean(),
  referencia_externa: z.string().max(255).optional(),
  documento_json: z.string().optional(),
  tipo_operacion: z.string().max(100).optional(),
  fecha_cierre_estimada: z
    .string()
    .optional()
    .refine((v) => !v || /^\d{4}-\d{2}-\d{2}$/.test(v), {
      message: 'La fecha debe tener formato YYYY-MM-DD',
    }),
});

export type MonedaInput = z.infer<typeof monedaSchema>;

// ── Transacción Financiera ─────────────────────────────────────────────────────

const tipoTransaccion = ['INGRESO', 'EGRESO', 'TRANSFERENCIA'] as const;

export const transaccionFinancieraSchema = z.object({
  tipo: z.enum(tipoTransaccion, {
    errorMap: () => ({ message: 'El tipo de transacción no es válido' }),
  }),
  id_cuenta_origen: z.string().optional(),
  id_cuenta_destino: z.string().optional(),
  monto: z
    .string()
    .min(1, 'El monto es obligatorio')
    .refine((v) => !isNaN(Number(v)) && Number(v) > 0, {
      message: 'El monto debe ser mayor a 0',
    }),
  id_moneda: z.string().min(1, 'La moneda es obligatoria'),
  fecha: z.string().min(1, 'La fecha es obligatoria'),
  concepto: z.string().min(1, 'El concepto es obligatorio').max(255),
  referencia: z.string().max(255).optional(),
});

export type TransaccionFinancieraInput = z.infer<typeof transaccionFinancieraSchema>;
