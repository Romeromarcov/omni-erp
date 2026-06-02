import { post, get } from './api';
import { toList } from '../utils/api';
import { isSimilar } from '../utils/fuzzyDuplicate';

export interface Cliente {
  id_cliente: string;
  razon_social: string;
  rif: string;
  telefono: string;
}

export async function crearCliente(data: Omit<Cliente, 'id_cliente'>): Promise<Cliente> {
  // El tipo ahora acepta id_empresa
  return await post('/crm/clientes/', data);
}

export interface ClienteCreate {
  razon_social: string;
  rif: string;
  telefono: string;
  id_empresa: string;
  [key: string]: unknown; // Index signature
}

export async function crearClienteConEmpresa(data: ClienteCreate): Promise<Cliente> {
  return await post('/crm/clientes/', data);
}

export async function buscarClientes(query: string, empresaId?: string): Promise<Cliente[]> {
  // Endpoint corregido para buscar clientes en el backend real, incluyendo empresa
  const empresaParam = empresaId ? `&empresa=${empresaId}` : '';
  const response: Cliente[] | { results: Cliente[] } = await get(`/crm/clientes/?search=${encodeURIComponent(query)}${empresaParam}`);
  return toList<Cliente>(response);
}

export async function buscarClientesSimilares(nombre: string, rif: string, empresaId?: string): Promise<Cliente[]> {
  if (!empresaId) return [];
  const response = await fetchClientes(empresaId);
  let clientes = toList<Cliente>(response);
  // Extraer tipo_rif (prefijo) del rif
  const tipoRifNuevo = rif.split('-')[0] || '';
  // Filtrar por similitud cruzada: nombre y rif similares al mismo cliente, y tipo_rif coincida
  clientes = clientes.filter(cli => {
    const tipoRifExistente = cli.rif.split('-')[0] || '';
    const nombreSimilar = nombre && isSimilar(nombre, cli.razon_social, 70);
    const rifSimilar = rif && isSimilar(rif, cli.rif, 80);
    const tipoCoincide = tipoRifNuevo === tipoRifExistente;
    return nombreSimilar && rifSimilar && tipoCoincide;
  });
  return clientes; // No limitar, devolver todos los que cumplan
}

export async function fetchClientes(empresaId: string): Promise<Cliente[] | { results: Cliente[] }> {
  return get<Cliente[] | { results: Cliente[] }>(`/crm/clientes/?empresa=${empresaId}`);
}
