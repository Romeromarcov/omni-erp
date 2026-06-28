/**
 * Schemas Zod para los formularios del subproyecto CxC Lubrikca
 * (react-hook-form + @hookform/resolvers/zod).
 *
 * Dinero/porcentajes/tolerancias viajan como string decimal (R-CODE-4): la
 * validación numérica se hace con decimal.js, nunca con float. Los porcentajes
 * son fracciones (0.030000 = 3 %).
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

const esDecimalPositivo = (v: string): boolean => {
  try {
    const d = new Decimal(v);
    return !d.isNaN() && d.greaterThan(0);
  } catch {
    return false;
  }
};

const decimalNoNegativo = (campo: string) =>
  z
    .string()
    .min(1, `${campo} es obligatorio`)
    .refine(esDecimalNoNegativo, { message: `${campo} debe ser un número ≥ 0` });

/**
 * Valida que `vigencia_hasta >= vigencia_desde` cuando ambas existen. Se aplica
 * vía `superRefine` para apuntar el error al campo `vigencia_hasta`.
 */
const refinarVigencia = <T extends { vigencia_desde?: string; vigencia_hasta?: string }>(
  data: T,
  ctx: z.RefinementCtx,
): void => {
  const { vigencia_desde, vigencia_hasta } = data;
  if (vigencia_desde && vigencia_hasta && vigencia_hasta < vigencia_desde) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Debe ser mayor o igual a la fecha desde',
      path: ['vigencia_hasta'],
    });
  }
};

const vigenciaCampos = {
  vigencia_desde: z.string().min(1, 'La fecha desde es obligatoria'),
  vigencia_hasta: z.string().optional().or(z.literal('')),
  activo: z.boolean().optional(),
};

// ── Descuentos Marca/Categoría ──────────────────────────────────────────────
export const descuentoMarcaSchema = z
  .object({
    marca: z.string().min(1, 'La marca es obligatoria').max(100),
    categoria: z.string().min(1, 'La categoría es obligatoria').max(100),
    tipo_descuento: z.string().min(1, 'El tipo es obligatorio'),
    porcentaje: decimalNoNegativo('El porcentaje'),
    ...vigenciaCampos,
  })
  .superRefine(refinarVigencia);
export type DescuentoMarcaInput = z.infer<typeof descuentoMarcaSchema>;

// ── Descuento BCV-Completo ──────────────────────────────────────────────────
export const descuentoBcvSchema = z
  .object({
    porcentaje: decimalNoNegativo('El porcentaje'),
    ...vigenciaCampos,
  })
  .superRefine(refinarVigencia);
export type DescuentoBcvInput = z.infer<typeof descuentoBcvSchema>;

// ── Promociones primera compra ──────────────────────────────────────────────
export const promocionSchema = z
  .object({
    producto: z.string().min(1, 'El producto es obligatorio').max(200),
    ...vigenciaCampos,
  })
  .superRefine(refinarVigencia);
export type PromocionInput = z.infer<typeof promocionSchema>;

// ── Reglas de recurrencia ───────────────────────────────────────────────────
export const reglaRecurrenciaSchema = z
  .object({
    condicion: z.string().min(1, 'La condición es obligatoria'),
    tipo_beneficio: z.string().min(1, 'El tipo de beneficio es obligatorio'),
    valor: decimalNoNegativo('El valor'),
    ...vigenciaCampos,
  })
  .superRefine(refinarVigencia);
export type ReglaRecurrenciaInput = z.infer<typeof reglaRecurrenciaSchema>;

// ── Feriados ─────────────────────────────────────────────────────────────────
export const feriadoSchema = z.object({
  fecha: z.string().min(1, 'La fecha es obligatoria'),
  descripcion: z.string().min(1, 'La descripción es obligatoria').max(200),
  tipo: z.string().min(1, 'El tipo es obligatorio'),
  activo: z.boolean().optional(),
});
export type FeriadoInput = z.infer<typeof feriadoSchema>;

// ── Métodos de pago ─────────────────────────────────────────────────────────
export const metodoPagoSchema = z.object({
  codigo: z.string().min(1, 'El código es obligatorio').max(50),
  nombre: z.string().min(1, 'El nombre es obligatorio').max(120),
  moneda: z.string().min(1, 'La moneda es obligatoria'),
  tipo_tasa: z.string().min(1, 'El tipo de tasa es obligatorio'),
  es_contado: z.boolean().optional(),
  activo: z.boolean().optional(),
});
export type MetodoPagoInput = z.infer<typeof metodoPagoSchema>;

// ── Tolerancias de conciliación ─────────────────────────────────────────────
export const configConciliacionSchema = z.object({
  tolerance_rounding: decimalNoNegativo('La tolerancia de redondeo'),
  tolerance_red: decimalNoNegativo('La tolerancia roja'),
});
export type ConfigConciliacionInput = z.infer<typeof configConciliacionSchema>;

// ── Registrar vinculación (Fase 6b) ─────────────────────────────────────────
export const registrarVinculacionSchema = z.object({
  pedido: z.string().min(1, 'El pedido es obligatorio'),
  pago: z.string().min(1, 'El pago es obligatorio'),
  monto_aplicado: z
    .string()
    .min(1, 'El monto es obligatorio')
    .refine(esDecimalPositivo, { message: 'El monto debe ser un número mayor a 0' }),
  hora_pago_confirmada: z.string().min(1, 'La hora del pago es obligatoria'),
  es_tasa_heredada: z.boolean().optional(),
});
export type RegistrarVinculacionInput = z.infer<typeof registrarVinculacionSchema>;

// ── Conciliar pedido (Fase 6b) ──────────────────────────────────────────────
export const conciliarSchema = z.object({
  pedido: z.string().min(1, 'El pedido es obligatorio'),
});
export type ConciliarInput = z.infer<typeof conciliarSchema>;
