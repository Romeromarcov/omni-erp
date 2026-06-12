/**
 * Schemas Zod para los formularios de Tesorería (react-hook-form + zod).
 * Los montos viajan como string decimal y se validan con decimal.js (R-CODE-4):
 * cero aritmética float sobre dinero.
 */
import { z } from 'zod';
import Decimal from 'decimal.js';

const esDecimal = (v: string): boolean => {
  try {
    return !new Decimal(v).isNaN();
  } catch {
    return false;
  }
};

const esDecimalPositivo = (v: string): boolean => esDecimal(v) && new Decimal(v).greaterThan(0);
const esDecimalNoNegativo = (v: string): boolean =>
  esDecimal(v) && new Decimal(v).greaterThanOrEqualTo(0);

// ── Operación de cambio de divisa ─────────────────────────────────────────────

export const operacionCambioSchema = z
  .object({
    numero_operacion: z.string().min(1, 'El número de operación es obligatorio').max(50, 'Máximo 50 caracteres'),
    fecha_operacion: z.string().min(1, 'La fecha es obligatoria'),
    tipo_operacion: z.string().min(1, 'El tipo de operación es obligatorio'),
    moneda_origen: z.string().min(1, 'La moneda origen es obligatoria'),
    moneda_destino: z.string().min(1, 'La moneda destino es obligatoria'),
    monto_origen: z
      .string()
      .min(1, 'El monto origen es obligatorio')
      .refine(esDecimalPositivo, { message: 'El monto debe ser un número mayor a 0' }),
    tasa_cambio: z
      .string()
      .min(1, 'La tasa de cambio es obligatoria')
      .refine(esDecimalPositivo, { message: 'La tasa debe ser un número mayor a 0' }),
    comision: z
      .string()
      .optional()
      .refine((v) => !v || esDecimalNoNegativo(v), { message: 'La comisión debe ser un número ≥ 0' }),
    metodo_pago_origen: z.string().min(1, 'El método de pago origen es obligatorio'),
    metodo_pago_destino: z.string().min(1, 'El método de pago destino es obligatorio'),
    caja_origen: z.string().optional(),
    caja_destino: z.string().optional(),
    referencia_transaccion_origen: z.string().max(100, 'Máximo 100 caracteres').optional(),
    referencia_transaccion_destino: z.string().max(100, 'Máximo 100 caracteres').optional(),
    observaciones: z.string().max(1000, 'Máximo 1000 caracteres').optional(),
  })
  .refine((data) => data.moneda_origen !== data.moneda_destino, {
    message: 'La moneda destino debe ser distinta de la origen',
    path: ['moneda_destino'],
  });

export type OperacionCambioInput = z.infer<typeof operacionCambioSchema>;

// ── Conciliación bancaria ─────────────────────────────────────────────────────

export const conciliacionSchema = z
  .object({
    id_cuenta_bancaria: z.string().min(1, 'La cuenta bancaria es obligatoria'),
    periodo_inicio: z.string().min(1, 'El inicio del período es obligatorio'),
    periodo_fin: z.string().min(1, 'El fin del período es obligatorio'),
    saldo_banco: z
      .string()
      .min(1, 'El saldo según banco es obligatorio')
      .refine(esDecimal, { message: 'El saldo debe ser un número' }),
    saldo_libro: z
      .string()
      .min(1, 'El saldo según libros es obligatorio')
      .refine(esDecimal, { message: 'El saldo debe ser un número' }),
    observaciones: z.string().max(1000, 'Máximo 1000 caracteres').optional(),
  })
  .refine((data) => data.periodo_inicio <= data.periodo_fin, {
    message: 'El fin del período no puede ser anterior al inicio',
    path: ['periodo_fin'],
  });

export type ConciliacionInput = z.infer<typeof conciliacionSchema>;
