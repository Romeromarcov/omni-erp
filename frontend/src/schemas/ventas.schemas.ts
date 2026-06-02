/**
 * GAP-11: Zod validation schemas for critical ventas forms.
 * Used with react-hook-form + @hookform/resolvers/zod.
 */
import { z } from 'zod';
import { subtotalLinea, sumDecimals } from '../lib/decimal';

/** Tolerancia de redondeo para comparaciones monetarias (1 céntimo). */
const MONTO_EPSILON = 0.01;

// ── Shared sub-schemas ────────────────────────────────────────────────────────

const requiredUUID = (label: string) =>
  z.string().min(1, { message: `${label} es obligatorio` });

// ── Detalle (línea de producto) ───────────────────────────────────────────────

export const detalleVentaSchema = z.object({
  id_producto: requiredUUID('Producto'),
  cantidad: z
    .string()
    .min(1, 'La cantidad es obligatoria')
    .refine((v) => !isNaN(Number(v)) && Number(v) > 0, {
      message: 'La cantidad debe ser mayor a 0',
    }),
  precio_unitario: z
    .string()
    .min(1, 'El precio unitario es obligatorio')
    .refine((v) => !isNaN(Number(v)) && Number(v) >= 0, {
      message: 'El precio unitario no puede ser negativo',
    }),
  descuento_porcentaje: z
    .string()
    .optional()
    .refine((v) => v === undefined || v === '' || (!isNaN(Number(v)) && Number(v) >= 0 && Number(v) <= 100), {
      message: 'El descuento debe estar entre 0 y 100',
    }),
});

export type DetalleVentaInput = z.infer<typeof detalleVentaSchema>;

// ── Pedido ────────────────────────────────────────────────────────────────────

export const pedidoSchema = z.object({
  fecha_pedido: z.string().min(1, 'La fecha del pedido es obligatoria'),
  id_empresa: requiredUUID('Empresa'),
  id_sucursal: requiredUUID('Sucursal'),
  id_cliente: z.string().optional(),
  id_caja: z.string().optional(),
  id_vendedor: z.string().optional(),
  observaciones: z.string().max(1000, 'Las observaciones no pueden superar 1000 caracteres').optional(),
  detalles: z
    .array(detalleVentaSchema)
    .min(1, 'El pedido debe tener al menos un producto'),
});

export type PedidoInput = z.infer<typeof pedidoSchema>;

// ── Cotización ────────────────────────────────────────────────────────────────

export const cotizacionSchema = z.object({
  fecha_cotizacion: z.string().min(1, 'La fecha de la cotización es obligatoria'),
  fecha_vencimiento: z.string().optional(),
  id_empresa: requiredUUID('Empresa'),
  id_sucursal: requiredUUID('Sucursal'),
  id_cliente: z.string().optional(),
  observaciones: z.string().max(1000).optional(),
  detalles: z
    .array(detalleVentaSchema)
    .min(1, 'La cotización debe tener al menos un producto'),
});

export type CotizacionInput = z.infer<typeof cotizacionSchema>;

// ── Nota de Venta ─────────────────────────────────────────────────────────────

export const notaVentaSchema = z.object({
  fecha_nota: z.string().min(1, 'La fecha de la nota de venta es obligatoria'),
  id_empresa: requiredUUID('Empresa'),
  id_sucursal: requiredUUID('Sucursal'),
  id_cliente: z.string().optional(),
  id_caja: z.string().optional(),
  observaciones: z.string().max(1000).optional(),
  detalles: z
    .array(detalleVentaSchema)
    .min(1, 'La nota de venta debe tener al menos un producto'),
});

export type NotaVentaInput = z.infer<typeof notaVentaSchema>;

// ── Factura Fiscal ────────────────────────────────────────────────────────────

export const facturaFiscalSchema = z.object({
  fecha_emision: z.string().min(1, 'La fecha de emisión es obligatoria'),
  id_empresa: requiredUUID('Empresa'),
  id_cliente: requiredUUID('Cliente'),
  condicion_pago: z.enum(['CONTADO', 'CREDITO'], {
    errorMap: () => ({ message: 'La condición de pago debe ser CONTADO o CREDITO' }),
  }),
  dias_credito: z
    .number()
    .int()
    .nonnegative('Los días de crédito no pueden ser negativos')
    .optional(),
  // FE-HIGH-8: monto_total es opcional; si está presente, debe cuadrar con los detalles.
  monto_total: z
    .union([z.string(), z.number()])
    .optional()
    .refine((v) => v === undefined || v === '' || !isNaN(Number(v)), {
      message: 'El monto total debe ser un número válido',
    }),
  observaciones: z.string().max(1000).optional(),
  detalles: z
    .array(detalleVentaSchema)
    .min(1, 'La factura debe tener al menos un producto'),
})
  .refine(
    (data) => data.condicion_pago !== 'CREDITO' || (data.dias_credito !== undefined && data.dias_credito > 0),
    {
      message: 'Los días de crédito son obligatorios cuando la condición de pago es CRÉDITO',
      path: ['dias_credito'],
    }
  )
  // FE-HIGH-8: validación cross-field — el total declarado debe cuadrar con la
  // suma de los subtotales de las líneas (calculada con decimal.js).
  .superRefine((data, ctx) => {
    if (data.monto_total === undefined || data.monto_total === '') return;
    const sumaDetalles = sumDecimals(
      data.detalles.map((d) =>
        subtotalLinea(d.cantidad, d.precio_unitario, d.descuento_porcentaje),
      ),
    );
    const declarado = Number(data.monto_total);
    if (sumaDetalles.minus(declarado).abs().greaterThan(MONTO_EPSILON)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'El total no cuadra con los detalles',
        path: ['monto_total'],
      });
    }
  });

export type FacturaFiscalInput = z.infer<typeof facturaFiscalSchema>;

// ── Nota de Crédito de Venta ────────────────────────────────────────────────────

const motivoNotaCredito = [
  'DEVOLUCION',
  'DESCUENTO',
  'ERROR_FACTURACION',
  'ANULACION',
  'OTRO',
] as const;

const estadoNotaCredito = ['BORRADOR', 'EMITIDA', 'APLICADA', 'ANULADA'] as const;

export const detalleNotaCreditoVentaSchema = z.object({
  id_producto: requiredUUID('Producto'),
  cantidad: z.coerce.number().positive('La cantidad debe ser mayor a 0'),
  precio_unitario: z.coerce.number().nonnegative('El precio unitario no puede ser negativo'),
});

export const notaCreditoVentaSchema = z.object({
  id_cliente: requiredUUID('Cliente'),
  fecha_emision: z.string().min(1, 'La fecha de emisión es obligatoria'),
  motivo: z.enum(motivoNotaCredito, {
    errorMap: () => ({ message: 'El motivo no es válido' }),
  }),
  estado: z.enum(estadoNotaCredito, {
    errorMap: () => ({ message: 'El estado no es válido' }),
  }),
  observaciones: z.string().max(1000).optional(),
  detalles: z
    .array(detalleNotaCreditoVentaSchema)
    .min(1, 'La nota de crédito debe tener al menos un producto'),
});

export type NotaCreditoVentaInput = z.infer<typeof notaCreditoVentaSchema>;
