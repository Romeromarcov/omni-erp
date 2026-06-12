/**
 * Schemas Zod para los formularios de Nómina (react-hook-form + zod).
 * Horas y montos viajan como string decimal (R-CODE-4): la validación numérica
 * se hace con decimal.js, nunca con float.
 */
import { z } from 'zod';
import Decimal from 'decimal.js';

const aDecimal = (v: string): Decimal | null => {
  try {
    const d = new Decimal(v);
    return d.isNaN() ? null : d;
  } catch {
    return null;
  }
};

/** '' cuenta como 0 (campo no tocado); si hay texto debe ser decimal ≥ 0. */
const esHorasValidas = (v: string): boolean => {
  if (v === '') return true;
  const d = aDecimal(v);
  return d !== null && d.greaterThanOrEqualTo(0);
};

const esDecimalPositivo = (v: string): boolean => {
  const d = aDecimal(v);
  return d !== null && d.greaterThan(0);
};

// ── Crear proceso de nómina ───────────────────────────────────────────────────

export const procesoNominaSchema = z.object({
  id_periodo_nomina: z.string().min(1, 'El período es obligatorio'),
  numero_proceso: z
    .string()
    .min(1, 'El número de proceso es obligatorio')
    .max(50, 'Máximo 50 caracteres'),
});

export type ProcesoNominaInput = z.infer<typeof procesoNominaSchema>;

// ── Crear período de nómina ───────────────────────────────────────────────────

export const periodoNominaSchema = z
  .object({
    nombre_periodo: z
      .string()
      .min(1, 'El nombre del período es obligatorio')
      .max(100, 'Máximo 100 caracteres'),
    tipo_periodo: z.enum(['SEMANAL', 'QUINCENAL', 'MENSUAL', 'ANUAL'], {
      errorMap: () => ({ message: 'El tipo de período es obligatorio' }),
    }),
    fecha_inicio: z.string().min(1, 'La fecha de inicio es obligatoria'),
    fecha_fin: z.string().min(1, 'La fecha de fin es obligatoria'),
    fecha_pago: z.string().min(1, 'La fecha de pago es obligatoria'),
  })
  .refine((p) => p.fecha_fin >= p.fecha_inicio, {
    message: 'La fecha de fin debe ser posterior o igual a la de inicio',
    path: ['fecha_fin'],
  });

export type PeriodoNominaInput = z.infer<typeof periodoNominaSchema>;

// ── Procesar: datos variables por empleado ────────────────────────────────────

export const filaProcesarEmpleadoSchema = z
  .object({
    /** String(id) del empleado — clave del body {"empleados": {...}}. */
    id_empleado: z.string().min(1),
    horas_extra_diurnas: z
      .string()
      .refine(esHorasValidas, { message: 'Debe ser un número de horas ≥ 0' }),
    horas_extra_nocturnas: z
      .string()
      .refine(esHorasValidas, { message: 'Debe ser un número de horas ≥ 0' }),
    /** Bono nocturno sí/no; el "sí" exige indicar las horas nocturnas (> 0). */
    bono_nocturno: z.boolean(),
    horas_nocturnas: z
      .string()
      .refine(esHorasValidas, { message: 'Debe ser un número de horas ≥ 0' }),
  })
  .superRefine((fila, ctx) => {
    if (fila.bono_nocturno && !esDecimalPositivo(fila.horas_nocturnas)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['horas_nocturnas'],
        message: 'Indique las horas nocturnas (> 0) para aplicar el bono',
      });
    }
  });

export type FilaProcesarEmpleadoInput = z.infer<typeof filaProcesarEmpleadoSchema>;

export const procesarNominaSchema = z.object({
  empleados: z.array(filaProcesarEmpleadoSchema),
});

export type ProcesarNominaInput = z.infer<typeof procesarNominaSchema>;
