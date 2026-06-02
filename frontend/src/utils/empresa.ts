// Utilidad para obtener el id_empresa activo.
// FE-HIGH-13: `id_empresa` es una selección de UI (no PII) y permanece en
// localStorage; el objeto completo de la empresa ya no se guarda allí.
export function getEmpresaId(): string | null {
  return localStorage.getItem('id_empresa') || null;
}
