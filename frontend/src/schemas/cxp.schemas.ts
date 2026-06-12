/**
 * Schemas Zod para formularios de CxP (react-hook-form + zod).
 * El monto viaja como string decimal (R-CODE-4): la validación numérica se
 * hace con decimal.js, nunca con float.
 */
import { z } from 'zod';
import Decimal from 'decimal.js';

const esDecimalPositivo = (v: string): boolean => {
  try {
    const d = new Decimal(v);
    return !d.isNaN() && d.greaterThan(0);
  } catch {
    return false;
  }
};

export const abonoCxpSchema = z.object({
  monto: z
    .string()
    .min(1, 'El monto es obligatorio')
    .refine(esDecimalPositivo, { message: 'El monto debe ser un número mayor a 0' }),
  descripcion: z.string().max(500, 'Máximo 500 caracteres').optional(),
});

export type AbonoCxpInput = z.infer<typeof abonoCxpSchema>;
