import { get, put, post, fetchText, fetchBlob } from './api';

// ── Types ────────────────────────────────────────────────────────────────────

export interface ConfiguracionFiscalEmpresa {
  id: string;
  id_empresa: string;
  contribuyente_iva: boolean;
  aplica_igtf: boolean;
  tasa_igtf: string;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface TasaIVAEmpresa {
  id: string;
  id_empresa: string;
  tipo: 'GENERAL' | 'REDUCIDO' | 'EXENTO' | 'ADICIONAL';
  nombre: string;
  tasa: string;
  activo: boolean;
  fecha_creacion: string;
}

export interface LibroEntry {
  rif_emisor: string;
  rif_receptor: string;
  fecha: string;
  nro_ctrl: string;
  nro_fac: string;
  base_imponible: string;
  iva: string;
  total: string;
}

// ── Configuración Fiscal ─────────────────────────────────────────────────────

export const configuracionFiscalService = {
  async getByEmpresa(empresaId: string): Promise<ConfiguracionFiscalEmpresa | null> {
    const resp = await get<{ count: number; results: ConfiguracionFiscalEmpresa[] }>(
      `/fiscal/configuracion-fiscal/?id_empresa=${empresaId}`
    );
    if (resp && 'results' in resp) return resp.results[0] ?? null;
    return null;
  },

  async update(id: string, data: Partial<ConfiguracionFiscalEmpresa>): Promise<ConfiguracionFiscalEmpresa> {
    return put<ConfiguracionFiscalEmpresa>(`/fiscal/configuracion-fiscal/${id}/`, data as Record<string, unknown>);
  },

  async create(data: Partial<ConfiguracionFiscalEmpresa>): Promise<ConfiguracionFiscalEmpresa> {
    return post<ConfiguracionFiscalEmpresa>('/fiscal/configuracion-fiscal/', data as Record<string, unknown>);
  },
};

// ── Tasas IVA ────────────────────────────────────────────────────────────────

export const tasaIVAService = {
  async getByEmpresa(empresaId: string): Promise<TasaIVAEmpresa[]> {
    const resp = await get<{ count: number; results: TasaIVAEmpresa[] }>(
      `/fiscal/tasas-iva/?id_empresa=${empresaId}`
    );
    if (resp && 'results' in resp) return resp.results;
    return [];
  },

  async update(id: string, data: Partial<TasaIVAEmpresa>): Promise<TasaIVAEmpresa> {
    return put<TasaIVAEmpresa>(`/fiscal/tasas-iva/${id}/`, data as Record<string, unknown>);
  },

  async create(data: Partial<TasaIVAEmpresa>): Promise<TasaIVAEmpresa> {
    return post<TasaIVAEmpresa>('/fiscal/tasas-iva/', data as Record<string, unknown>);
  },
};

// ── Libros SENIAT ────────────────────────────────────────────────────────────

function parseTxt(txt: string): LibroEntry[] {
  const lines = txt.trim().split('\n');
  if (lines.length < 2) return [];
  return lines.slice(1).map((line) => {
    const [rif_emisor = '', rif_receptor = '', fecha = '', nro_ctrl = '', nro_fac = '',
           base_imponible = '', iva = '', total = ''] = line.split('|');
    return { rif_emisor, rif_receptor, fecha, nro_ctrl, nro_fac, base_imponible, iva, total };
  });
}

async function fetchLibroTxt(tipo: 'ventas' | 'compras', empresaId: string, periodo: string): Promise<LibroEntry[]> {
  const endpoint = `/fiscal/libro-${tipo}/?empresa=${empresaId}&periodo=${periodo}`;
  const txt = await fetchText(endpoint, { headers: { Accept: 'text/plain' } });
  return parseTxt(txt);
}

async function downloadLibroTxt(tipo: 'ventas' | 'compras', empresaId: string, periodo: string): Promise<void> {
  const endpoint = `/fiscal/libro-${tipo}/?empresa=${empresaId}&periodo=${periodo}`;
  const blob = await fetchBlob(endpoint, { headers: { Accept: 'text/plain' } });
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objUrl;
  a.download = `libro_${tipo}_${periodo}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(objUrl);
}

export const libroService = {
  fetchLibroVentasTxt: (empresaId: string, periodo: string) =>
    fetchLibroTxt('ventas', empresaId, periodo),
  fetchLibroComprasTxt: (empresaId: string, periodo: string) =>
    fetchLibroTxt('compras', empresaId, periodo),
  downloadLibroVentasTxt: (empresaId: string, periodo: string) =>
    downloadLibroTxt('ventas', empresaId, periodo),
  downloadLibroComprasTxt: (empresaId: string, periodo: string) =>
    downloadLibroTxt('compras', empresaId, periodo),
};
