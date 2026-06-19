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

// ── Plan de suscripción (billing SaaS) ─────────────────────────────────────────

// Acepta enteros/decimales con punto, hasta 2 decimales. Rechaza negativos.
// Los precios se manejan como STRING decimal (R-CODE-4), nunca float.
// eslint-disable-next-line security/detect-unsafe-regex -- FP del heurístico star-height de safe-regex: `\.` y `\d` son disjuntos, sin backtracking ambiguo (matching lineal)
const DECIMAL_RE = /^\d+(\.\d{1,2})?$/;

const limiteNoNegativo = z.coerce
  .number()
  .int('El límite debe ser un entero')
  .min(0, 'Los límites no pueden ser negativos (use 0 para ilimitado).');

export const planSchema = z.object({
  nombre: z.string().trim().min(1, 'El nombre es obligatorio').max(100),
  nivel: z.enum(['FREE', 'STARTER', 'PRO', 'ENTERPRISE']),
  descripcion: z.string().max(500).optional().or(z.literal('')),
  precio_mensual: z
    .string()
    .regex(DECIMAL_RE, 'Precio mensual inválido (use formato 0.00, sin negativos).'),
  precio_anual: z
    .string()
    .regex(DECIMAL_RE, 'Precio anual inválido (use formato 0.00, sin negativos).'),
  max_usuarios: limiteNoNegativo,
  max_empresas: limiteNoNegativo,
  max_documentos_mes: limiteNoNegativo,
  permite_ia: z.boolean(),
  permite_api: z.boolean(),
  permite_reportes_avanzados: z.boolean(),
  permite_multimoneda: z.boolean(),
  soporte: z.enum(['email', 'chat', 'telefono', 'dedicado']),
  activo: z.boolean(),
});

export type PlanInput = z.infer<typeof planSchema>;
