/**
 * Esquemas de validación Zod para formularios del módulo SaaS (admin).
 * Se usan con react-hook-form + @hookform/resolvers/zod (mode: 'onBlur').
 */
import { z } from 'zod';

// ── Proveedor de integración (conector del Integration Hub) ────────────────────

/** Estados válidos de un proveedor (espejo de integrationHubService.ProveedorEstado). */
export const ESTADOS_PROVEEDOR = ['activo', 'beta', 'proximamente'] as const;

/** El código identifica al conector en el backend: minúsculas, números, guion bajo. */
const CODIGO_RE = /^[a-z0-9_]+$/;

export const proveedorIntegracionSchema = z.object({
  codigo: z
    .string()
    .trim()
    .min(1, 'El código es obligatorio')
    .max(50, 'El código no puede superar 50 caracteres')
    .refine((v) => CODIGO_RE.test(v.toLowerCase()), {
      message:
        "El código solo admite minúsculas, números y guion bajo (ej: 'odoo', 'google_sheets').",
    }),
  nombre: z
    .string()
    .trim()
    .min(1, 'El nombre es obligatorio')
    .max(100, 'El nombre no puede superar 100 caracteres'),
  descripcion: z.string().max(500).optional().or(z.literal('')),
  icono_url: z.string().max(255).optional().or(z.literal('')),
  estado: z.enum(ESTADOS_PROVEEDOR),
  orden: z.coerce.number().int('El orden debe ser un entero').min(0, 'El orden no puede ser negativo'),
  capacidades: z.array(z.string()),
  /** Versiones soportadas como texto separado por coma; se normaliza al enviar. */
  versionesText: z.string().optional().or(z.literal('')),
  requiere_url: z.boolean(),
  requiere_db: z.boolean(),
  activo: z.boolean(),
});

export type ProveedorIntegracionInput = z.infer<typeof proveedorIntegracionSchema>;

/** Parte el texto de versiones en una lista limpia (sin vacíos ni espacios). */
export function parseVersiones(texto: string | undefined): string[] {
  return (texto ?? '')
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean);
}
