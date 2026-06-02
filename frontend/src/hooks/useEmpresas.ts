import { useQuery } from '@tanstack/react-query';
import { fetchEmpresas, type Empresa } from '../services/empresas';

/**
 * Hook que expone las empresas visibles para el usuario actual.
 * Reutiliza el servicio existente `fetchEmpresas` (services/empresas.ts).
 */
export function useEmpresas() {
  return useQuery<Empresa[], Error>({
    queryKey: ['empresas', 'visible'],
    queryFn: fetchEmpresas,
  });
}
