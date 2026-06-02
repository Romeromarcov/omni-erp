import { useCallback, useRef, useState } from 'react';
import { streamSSE } from '../services/api';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

/**
 * Chat conversacional con el asistente del ERP.
 * Hace streaming SSE contra POST /api/agentes/chat/.
 */
export function useAssistantChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setError(null);
    setStreaming(false);
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
  }, []);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || streaming) return;

      setError(null);
      const history: ChatMessage[] = [...messages, { role: 'user', content: trimmed }];
      // Añadimos el mensaje del usuario y un placeholder del asistente.
      setMessages([...history, { role: 'assistant', content: '' }]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const appendToLast = (chunk: string) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === 'assistant') {
            next[next.length - 1] = { ...last, content: last.content + chunk };
          }
          return next;
        });
      };

      try {
        await streamSSE(
          '/agentes/chat/',
          (event) => {
            if (event.text) appendToLast(event.text as string);
            if (event.error) setError(event.error as string);
          },
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: history }),
            signal: controller.signal,
          },
        );
      } catch (e: unknown) {
        if ((e as Error)?.name === 'AbortError') return;
        setError(e instanceof Error ? e.message : 'Error desconocido');
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [messages, streaming],
  );

  return { messages, streaming, error, send, stop, reset };
}
