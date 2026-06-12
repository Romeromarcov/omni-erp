/**
 * Schemas Zod para los formularios de RRHH (react-hook-form + zod).
 * El salario viaja como string decimal (R-CODE-4): la validación numérica se
 * hace con decimal.js, nunca con float.
 */
import { z } from 'zod';
import Decimal from 'decimal.js';

const esDecimalNoNegativo = (v: string): boolean => {
  try {
    const d = new Decimal(v);
    return !d.isNaN() && d.greaterThanOrEqualTo(0);
  } catch {
    return false;
  }
};

export const empleadoSchema = z.object({
  nombre: z.string().min(1, 'El nombre es obligatorio').max(100, 'Máximo 100 caracteres'),
  apellido: z.string().min(1, 'El apellido es obligatorio').max(100, 'Máximo 100 caracteres'),
  cedula: z.string().min(1, 'La cédula es obligatoria').max(20, 'Máximo 20 caracteres'),
  /** id del cargo como string del select; '' = sin cargo (FK nullable). */
  cargo: z.string(),
  fecha_ingreso: z.string().min(1, 'La fecha de ingreso es obligatoria'),
  /** Opcional; si se indica debe ser decimal ≥ 0 (va a documento_json.salario_mensual). */
  salario_mensual: z
    .string()
    .refine((v) => v === '' || esDecimalNoNegativo(v), {
      message: 'El salario debe ser un número ≥ 0',
    }),
  activo: z.boolean(),
});

export type EmpleadoInput = z.infer<typeof empleadoSchema>;
