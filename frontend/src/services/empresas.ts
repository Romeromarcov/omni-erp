import { get } from './api';

export interface Empresa {
  id_empresa: string;
  nombre_legal: string;
  nombre_comercial: string;
  identificador_fiscal: string;
  email_contacto: string;
  activo: boolean;
  fecha_registro: string;
}

export async function fetchEmpresas(): Promise<Empresa[]> {
  return get<Empresa[]>('/core/empresas/');
}
