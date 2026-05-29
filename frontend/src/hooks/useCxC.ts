import { useState, useEffect, useCallback } from 'react';
import { get } from '../services/api';
import type { CarteraAging, AcuerdoPago } from '../types/cxc';

// Hook para el dashboard de cartera
export function useCarteraDashboard() {
  const [data, setData] = useState<CarteraAging | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    get<CarteraAging>('/cobranza/cartera/dashboard/')
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return { data, loading, error, refresh };
}

// Hook para tasa de hoy (apunta a finanzas, NO a cobranza)
export function useTasaHoy() {
  const [tasa, setTasa] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    get<{ results: Array<{ valor_tasa: string; tipo_tasa: string; fecha_tasa: string }> }>(
      '/finanzas/tasas-cambio/?tipo_tasa=OFICIAL_BCV&ordering=-fecha_creacion&limit=1'
    )
      .then(data => {
        const hoy = new Date().toISOString().split('T')[0];
        const tasaHoy = data.results?.find(t => t.fecha_tasa === hoy);
        setTasa(tasaHoy?.valor_tasa ?? null);
      })
      .catch(() => setTasa(null))
      .finally(() => setLoading(false));
  }, []);

  return { tasa, loading };
}

// Hook para lista de acuerdos
export function useAcuerdos(estado?: string) {
  const endpoint = estado
    ? `/cobranza/acuerdos/?estado=${estado}`
    : '/cobranza/acuerdos/';
  const [data, setData] = useState<{ results: AcuerdoPago[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    get<{ results: AcuerdoPago[] }>(endpoint)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [endpoint]);

  useEffect(() => { refresh(); }, [refresh]);

  return { data, loading, error, refresh };
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
