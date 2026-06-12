/**
 * Schemas Zod para los formularios de Compras (react-hook-form + zod).
 * Los montos viajan como string decimal (R-CODE-4): la validación numérica se
 * hace con decimal.js, nunca con float.
 *
 * (Reescrito en el workstream F: los schemas previos de GAP-11 no coincidían
 * con el contrato real del backend `apps/compras` y no tenían consumidores.)
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

// ── Línea de orden de compra ──────────────────────────────────────────────────

export const lineaOrdenCompraSchema = z.object({
  id_producto: z.string().min(1, 'El producto es obligatorio'),
  cantidad: z
    .string()
    .min(1, 'La cantidad es obligatoria')
    .refine(esDecimalPositivo, { message: 'La cantidad debe ser un número mayor a 0' }),
  precio_unitario: z
    .string()
    .min(1, 'El precio unitario es obligatorio')
    .refine(esDecimalNoNegativo, { message: 'El precio debe ser un número ≥ 0' }),
});

export type LineaOrdenCompraInput = z.infer<typeof lineaOrdenCompraSchema>;

// ── Orden de compra (cabecera + líneas) ───────────────────────────────────────

export const ordenCompraSchema = z.object({
  id_proveedor: z.string().min(1, 'El proveedor es obligatorio'),
  numero_orden: z.string().min(1, 'El número de orden es obligatorio').max(50, 'Máximo 50 caracteres'),
  fecha_orden: z.string().min(1, 'La fecha de la orden es obligatoria'),
  observaciones: z.string().max(1000, 'Máximo 1000 caracteres').optional(),
  detalles: z.array(lineaOrdenCompraSchema).min(1, 'La orden debe tener al menos un producto'),
});

export type OrdenCompraInput = z.infer<typeof ordenCompraSchema>;

// ── Recepción de mercancía ────────────────────────────────────────────────────

export const itemRecepcionSchema = z.object({
  producto_id: z.string().min(1, 'El producto es obligatorio'),
  cantidad: z
    .string()
    .min(1, 'La cantidad es obligatoria')
    .refine(esDecimalPositivo, { message: 'La cantidad debe ser un número mayor a 0' }),
  costo_unitario: z
    .string()
    .min(1, 'El costo unitario es obligatorio')
    .refine(esDecimalNoNegativo, { message: 'El costo debe ser un número ≥ 0' }),
});

export const recepcionSchema = z.object({
  almacen_id: z.string().min(1, 'El almacén es obligatorio'),
  items: z.array(itemRecepcionSchema).min(1, 'La recepción debe tener al menos un producto'),
});

export type RecepcionInput = z.infer<typeof recepcionSchema>;

// ── Factura de compra ─────────────────────────────────────────────────────────

export const facturaCompraSchema = z.object({
  recepcion_id: z.string().min(1, 'La recepción es obligatoria'),
  numero_factura: z
    .string()
    .min(1, 'El número de factura es obligatorio')
    .max(50, 'Máximo 50 caracteres'),
  fecha_emision: z.string().optional(),
});

export type FacturaCompraInput = z.infer<typeof facturaCompraSchema>;
