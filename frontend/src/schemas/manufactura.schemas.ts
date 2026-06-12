/**
 * Schemas Zod para los formularios de Manufactura (react-hook-form + zod).
 * Montos y cantidades viajan como string decimal (R-CODE-4): la validación
 * numérica se hace con decimal.js, nunca con float.
 */
import { z } from 'zod';
import Decimal from 'decimal.js';

/** '' es válido (campo opcional); si hay valor debe ser decimal ≥ 0. */
const esDecimalNoNegativoOVacio = (v: string): boolean => {
  if (v === '') return true;
  try {
    const d = new Decimal(v);
    return !d.isNaN() && d.greaterThanOrEqualTo(0);
  } catch {
    return false;
  }
};

const esDecimalPositivoOVacio = (v: string): boolean => {
  if (v === '') return true;
  try {
    const d = new Decimal(v);
    return !d.isNaN() && d.greaterThan(0);
  } catch {
    return false;
  }
};

const campoDecimal = (mensaje: string) =>
  z.string().refine(esDecimalNoNegativoOVacio, { message: mensaje });

export const avanzarEtapaSchema = z.object({
  horas_trabajadas: campoDecimal('Las horas deben ser un número mayor o igual a 0'),
  tarifa_hora: campoDecimal('La tarifa debe ser un número mayor o igual a 0'),
  cantidad_destajo: campoDecimal('La cantidad a destajo debe ser un número mayor o igual a 0'),
  observaciones: z.string().max(500, 'Máximo 500 caracteres'),
});

export type AvanzarEtapaInput = z.infer<typeof avanzarEtapaSchema>;

export const completarOrdenSchema = z.object({
  almacen_id: z.string().min(1, 'El almacén es obligatorio'),
  cantidad: z
    .string()
    .refine(esDecimalPositivoOVacio, { message: 'La cantidad debe ser un número mayor a 0' }),
});

export type CompletarOrdenInput = z.infer<typeof completarOrdenSchema>;
