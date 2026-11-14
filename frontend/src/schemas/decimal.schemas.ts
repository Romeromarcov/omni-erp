/**
 * R-CODE-4: dinero y cantidades como string decimal, nunca como float de JavaScript.
 *
 * El backend declara estos campos como `string/decimal` (DRF DecimalField). Convertir lo que
 * escribe el usuario con `z.coerce.number()` los pasa a float y se pierde precisión a partir de
 * ~15 cifras significativas (p. ej. 0.1 o montos grandes con 4 decimales). Estos helpers validan
 * con decimal.js (exacto) y devuelven el MISMO string que escribió el usuario, para que viaje al
 * backend sin pasar por `number`.
 *
 * Formato aceptado: signo `-` opcional, dígitos y parte decimal opcional (`10`, `10.5`,
 * `0.0001`, `-3`). Se rechazan `+`, exponente (`1e3`), separador de miles, coma decimal y
 * espacios internos. El signo se acepta a propósito: así un valor negativo recibe el mensaje de
 * "no puede ser negativo" y no el de formato inválido.
 */
import Decimal from 'decimal.js';
import { z } from 'zod';

const SOLO_DIGITOS = /^\d+$/;

/**
 * Decimal exacto de un string decimal válido, o `null` si el formato no es válido.
 * Se valida por partes (entera y decimal) y no con una sola regex con grupo opcional repetido.
 */
function parsear(valor: string): Decimal | null {
  const sinSigno = valor.startsWith('-') ? valor.slice(1) : valor;
  const partes = sinSigno.split('.');
  if (partes.length > 2 || !partes.every((p) => SOLO_DIGITOS.test(p))) return null;
  return new Decimal(valor);
}

/** Base: string sin espacios en los extremos, no vacío y con formato decimal válido. */
const base = (requerido: string, invalido: string) =>
  z
    .string()
    .trim()
    .min(1, requerido)
    .refine((v) => parsear(v) !== null, { message: invalido });

/** Decimal estrictamente mayor que 0 (p. ej. cantidades). `mensaje` cubre formato y valor. */
export const decimalPositivo = (requerido: string, mensaje: string) =>
  base(requerido, mensaje).refine((v) => parsear(v)?.gt(0) ?? false, { message: mensaje });

/** Decimal mayor o igual a 0 (p. ej. precios). `mensaje` cubre formato y valor. */
export const decimalNoNegativo = (requerido: string, mensaje: string) =>
  base(requerido, mensaje).refine((v) => parsear(v)?.gte(0) ?? false, { message: mensaje });

/** Mensajes de `decimalEntre`: cada causa de rechazo conserva su propio texto. */
export interface MensajesRango {
  requerido: string;
  invalido: string;
  bajoElMinimo: string;
  sobreElMaximo: string;
}

/** Decimal entre `min` y `max`, ambos incluidos (p. ej. porcentaje de descuento). */
export const decimalEntre = (min: number, max: number, mensajes: MensajesRango) =>
  base(mensajes.requerido, mensajes.invalido)
    .refine((v) => parsear(v)?.gte(min) ?? true, { message: mensajes.bajoElMinimo })
    .refine((v) => parsear(v)?.lte(max) ?? true, { message: mensajes.sobreElMaximo });
