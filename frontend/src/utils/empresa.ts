// Utilidad para obtener el id_empresa actual de localStorage de forma segura
export function getEmpresaId(): string | null {
  try {
    const empresaStr = localStorage.getItem('empresa');
    if (!empresaStr) return null;
    const empresa = JSON.parse(empresaStr);
    return empresa.id_empresa || null;
  } catch {
    return null;
  }
}
