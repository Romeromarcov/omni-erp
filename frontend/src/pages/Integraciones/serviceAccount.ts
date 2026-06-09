/**
 * Validación del JSON de cuenta de servicio de Google usado por el conector
 * Google Sheets. Vive en su propio módulo para poder testearlo sin romper la
 * regla react-refresh/only-export-components del componente.
 */
export function parseServiceAccount(
  raw: string,
): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  const trimmed = raw.trim();
  if (!trimmed) return { ok: false, error: 'Pega el JSON de la cuenta de servicio.' };
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return { ok: false, error: 'El JSON no es válido. Revisa que lo hayas pegado completo.' };
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return { ok: false, error: 'El JSON debe ser un objeto de cuenta de servicio.' };
  }
  const obj = parsed as Record<string, unknown>;
  if (obj.type !== 'service_account' || !obj.client_email || !obj.private_key) {
    return {
      ok: false,
      error: 'No parece una cuenta de servicio (faltan type, client_email o private_key).',
    };
  }
  return { ok: true, value: obj };
}
