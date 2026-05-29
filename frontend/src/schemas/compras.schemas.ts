/**
 * GAP-11: Zod validation schemas for compras (purchase) forms.
 */
import { z } from 'zod';

// ── Detalle de compra ─────────────────────────────────────────────────────────

export const detalleCompraSchema = z.object({
  id_producto: z.string().min(1, 'El producto es obligatorio'),
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

export type DetalleCompraInput = z.infer<typeof detalleCompraSchema>;

// ── Orden de Compra ───────────────────────────────────────────────────────────

export const ordenCompraSchema = z.object({
  fecha_orden: z.string().min(1, 'La fecha de la orden es obligatoria'),
  fecha_entrega_esperada: z.string().optional(),
  id_empresa: z.string().min(1, 'La empresa es obligatoria'),
  id_proveedor: z.string().min(1, 'El proveedor es obligatorio'),
  condicion_pago: z.enum(['CONTADO', 'CREDITO']).default('CONTADO'),
  observaciones: z.string().max(1000).optional(),
  detalles: z
    .array(detalleCompraSchema)
    .min(1, 'La orden debe tener al menos un producto'),
});

export type OrdenCompraInput = z.infer<typeof ordenCompraSchema>;

// ── Factura de Compra ─────────────────────────────────────────────────────────

export const facturaCompraSchema = z.object({
  numero_factura: z.string().min(1, 'El número de factura es obligatorio'),
  fecha_factura: z.string().min(1, 'La fecha de factura es obligatoria'),
  id_empresa: z.string().min(1, 'La empresa es obligatoria'),
  id_proveedor: z.string().min(1, 'El proveedor es obligatorio'),
  condicion_pago: z.enum(['CONTADO', 'CREDITO']).default('CONTADO'),
  observaciones: z.string().max(1000).optional(),
  detalles: z
    .array(detalleCompraSchema)
    .min(1, 'La factura debe tener al menos un producto'),
});

export type FacturaCompraInput = z.infer<typeof facturaCompraSchema>;
