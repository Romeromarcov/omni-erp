import { useQuery, type UseQueryOptions } from '@tanstack/react-query';
import { get } from '../services/api';

/**
 * Hook genérico que envuelve useQuery de TanStack Query sobre el fetcher
 * existente (services/api.ts). Centraliza auth, retry y staleTime.
 *
 * @param endpoint  Path relativo de la API (ej. '/core/empresas/')
 * @param options   Opciones adicionales de useQuery (enabled, select, etc.)
 *
 * @example
 *   const { data, isLoading, error } = useApiQuery<Empresa[]>('/core/empresas/');
 */
export function useApiQuery<T>(
  endpoint: string,
  options?: Omit<UseQueryOptions<T, Error>, 'queryKey' | 'queryFn'>
) {
  return useQuery<T, Error>({
    queryKey: [endpoint],
    queryFn: () => get<T>(endpoint),
    ...options,
  });
}
