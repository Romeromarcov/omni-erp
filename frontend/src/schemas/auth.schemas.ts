/**
 * FE-CRIT-1: Zod validation schemas for auth/profile forms.
 * Used with react-hook-form + @hookform/resolvers/zod.
 */
import { z } from 'zod';

export const loginSchema = z.object({
  username: z.string().trim().min(1, 'El usuario es obligatorio'),
  password: z.string().min(1, 'La contraseña es obligatoria'),
});

export type LoginInput = z.infer<typeof loginSchema>;

export const profileSchema = z.object({
  first_name: z.string().trim().min(1, 'El nombre es obligatorio').max(150),
  last_name: z.string().trim().min(1, 'El apellido es obligatorio').max(150),
  email: z
    .string()
    .trim()
    .min(1, 'El correo es obligatorio')
    .email('El correo no es válido'),
  id_sucursal_predeterminada: z.string().min(1, 'La sucursal predeterminada es obligatoria'),
});

export type ProfileInput = z.infer<typeof profileSchema>;
