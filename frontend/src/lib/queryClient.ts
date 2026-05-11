import { QueryClient } from '@tanstack/react-query';

/**
 * Instancia global de QueryClient.
 * Configuración conservadora para un ERP:
 *  - staleTime 30s: los datos de lista se consideran frescos por 30 segundos.
 *  - retry 1: un solo reintento en error de red; los 401 los maneja api.ts.
 *  - refetchOnWindowFocus false: evita requests inesperados al volver al tab.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
