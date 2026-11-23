/**
 * Schemas Zod para los formularios de Contabilidad (react-hook-form + zod).
 * Los montos viajan como string decimal (R-CODE-4).
 */
import { z } from 'zod';

export const cuentaContableSchema = z.object({
  codigo_cuenta: z.string().min(1, 'El código es obligatorio').max(50, 'Máximo 50 caracteres'),
  nombre_cuenta: z.string().min(1, 'El nombre es obligatorio').max(255, 'Máximo 255 caracteres'),
  tipo_cuenta: z.string().min(1, 'El tipo de cuenta es obligatorio'),
  naturaleza: z.string().min(1, 'La naturaleza es obligatoria'),
  id_cuenta_padre: z.string().optional(),
});

export type CuentaContableInput = z.infer<typeof cuentaContableSchema>;

export const mapeoContableSchema = z.object({
  tipo_asiento: z.string().min(1, 'El tipo de asiento es obligatorio'),
  cuenta_debe: z.string().min(1, 'La cuenta del Debe es obligatoria'),
  cuenta_haber: z.string().min(1, 'La cuenta del Haber es obligatoria'),
  descripcion_plantilla: z.string().max(255, 'Máximo 255 caracteres').optional(),
});

export type MapeoContableInput = z.infer<typeof mapeoContableSchema>;

export const diarioContableSchema = z.object({
  codigo: z.string().min(1, 'El código es obligatorio').max(20, 'Máximo 20 caracteres'),
  nombre: z.string().min(1, 'El nombre es obligatorio').max(120, 'Máximo 120 caracteres'),
  tipo: z.string().min(1, 'El tipo es obligatorio'),
  ambito: z.enum(['FISCAL', 'GERENCIAL']).optional(),
  prefijo_secuencia: z.string().max(20, 'Máximo 20 caracteres').optional(),
  siguiente_numero: z
    .string()
    .regex(/^\d*$/, 'Debe ser un número entero positivo')
    .optional(),
  cuenta_defecto_debe: z.string().optional(),
  cuenta_defecto_haber: z.string().optional(),
});

export type DiarioContableInput = z.infer<typeof diarioContableSchema>;
