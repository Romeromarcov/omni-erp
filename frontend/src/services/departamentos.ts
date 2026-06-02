import { get } from './api';

export type Departamento = {
  id_departamento: string;
  nombre_departamento: string;
};

export async function fetchDepartamentos(): Promise<Departamento[]> {
  const res = await get<{ results: Departamento[] } | Departamento[]>('/core/departamentos/');
  if (Array.isArray(res)) return res;
  if (res && Array.isArray(res.results)) return res.results;
  return [];
}
