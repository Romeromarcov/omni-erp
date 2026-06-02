import { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { get } from '../services/api';
import type { CarteraAging, AcuerdoPago } from '../types/cxc';

// Hook para el dashboard de cartera
export function useCarteraDashboard() {
  const query = useQuery<CarteraAging>({
    queryKey: ['cartera', 'dashboard'],
    queryFn: () => get<CarteraAging>('/cobranza/cartera/dashboard/'),
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? (query.error as Error).message : null,
    refresh: query.refetch,
  };
}

// Hook para tasa de hoy (apunta a finanzas, NO a cobranza)
export function useTasaHoy() {
  const query = useQuery<string | null>({
    queryKey: ['tasas', 'hoy'],
    queryFn: async () => {
      const data = await get<{ results: Array<{ valor_tasa: string; tipo_tasa: string; fecha_tasa: string }> }>(
        '/finanzas/tasas-cambio/?tipo_tasa=OFICIAL_BCV&ordering=-fecha_creacion&limit=1'
      );
      const hoy = new Date().toISOString().split('T')[0];
      const tasaHoy = data.results?.find(t => t.fecha_tasa === hoy);
      return tasaHoy?.valor_tasa ?? null;
    },
  });

  return { tasa: query.data ?? null, loading: query.isLoading };
}

// Hook para lista de acuerdos
export function useAcuerdos(estado?: string) {
  const endpoint = estado
    ? `/cobranza/acuerdos/?estado=${estado}`
    : '/cobranza/acuerdos/';

  const query = useQuery<{ results: AcuerdoPago[] }>({
    queryKey: ['acuerdos', estado ?? null],
    queryFn: () => get<{ results: AcuerdoPago[] }>(endpoint),
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? (query.error as Error).message : null,
    refresh: query.refetch,
  };
}

// Helper de invalidación para mutaciones de CxC (creación de acuerdos, etc.)
// Permite refrescar dashboard de cartera y listas de acuerdos tras una escritura.
export function useInvalidateCxC() {
  const queryClient = useQueryClient();
  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['cartera'] });
    queryClient.invalidateQueries({ queryKey: ['acuerdos'] });
    queryClient.invalidateQueries({ queryKey: ['tasas'] });
  }, [queryClient]);
}

// Hook para streaming del agente
export function useAgenteStream() {
  const [streaming, setStreaming] = useState(false);
  const [output, setOutput] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const iniciar = useCallback(async (accion: 'analizar_cartera' | 'gestionar_cliente', params: Record<string, unknown> = {}) => {
    const token = localStorage.getItem('token');
    setStreaming(true);
    setOutput('');
    setError(null);

    try {
      const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
      const resp = await fetch(`${baseUrl}/cobranza/agente/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ accion, ...params }),
      });

      if (!resp.ok) {
        throw new Error(`Error ${resp.status}`);
      }

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') break;
            try {
              const parsed = JSON.parse(data);
              if (parsed.text) setOutput(prev => prev + parsed.text);
              if (parsed.error) setError(parsed.error);
            } catch {
              /* fragmento SSE parcial; se completa en la próxima iteración */
            }
          }
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error desconocido');
    } finally {
      setStreaming(false);
    }
  }, []);

  const limpiar = useCallback(() => {
    setOutput('');
    setError(null);
  }, []);

  return { streaming, output, error, iniciar, limpiar };
}
