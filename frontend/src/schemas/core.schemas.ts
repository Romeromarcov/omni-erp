/**
 * Esquemas de validación Zod para formularios del módulo Core.
 * Se usan con react-hook-form + @hookform/resolvers/zod (mode: 'onBlur').
 */
import { z } from 'zod';

// ── Departamento ──────────────────────────────────────────────────────────────
export const departamentoSchema = z.object({
  nombre_departamento: z
    .string()
    .min(2, 'El nombre debe tener al menos 2 caracteres')
    .max(100, 'El nombre no puede superar 100 caracteres'),
  descripcion: z.string().min(1, 'La descripción es obligatoria').max(500),
  activo: z.boolean(),
});

export type DepartamentoInput = z.infer<typeof departamentoSchema>;

// ── Sucursal ──────────────────────────────────────────────────────────────────
export const sucursalSchema = z.object({
  nombre: z
    .string()
    .min(2, 'El nombre debe tener al menos 2 caracteres')
    .max(100, 'El nombre no puede superar 100 caracteres'),
  codigo_sucursal: z.string().min(1, 'El código es obligatorio').max(50),
  direccion: z.string().min(1, 'La dirección es obligatoria').max(255),
  telefono: z.string().min(1, 'El teléfono es obligatorio').max(50),
  email_contacto: z
    .string()
    .max(255)
    .optional()
    .or(z.literal(''))
    .refine((v) => !v || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v), {
      message: 'El email no es válido',
    }),
  ubicacion_gps_json: z.string().max(500).optional().or(z.literal('')),
  activo: z.boolean(),
});

export type SucursalInput = z.infer<typeof sucursalSchema>;

// ── Empresa ───────────────────────────────────────────────────────────────────
export const empresaSchema = z.object({
  nombre_legal: z
    .string()
    .min(2, 'El nombre legal debe tener al menos 2 caracteres')
    .max(255),
  nombre_comercial: z.string().min(1, 'El nombre comercial es obligatorio').max(255),
  identificador_fiscal: z.string().min(1, 'El identificador fiscal es obligatorio').max(50),
  email_contacto: z
    .string()
    .min(1, 'El email es obligatorio')
    .email('El email no es válido')
    .max(255),
  activo: z.boolean(),
  id_moneda_base: z.string().min(1, 'Debe seleccionar una moneda base'),
});

export type EmpresaInput = z.infer<typeof empresaSchema>;
