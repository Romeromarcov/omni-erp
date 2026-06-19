import { useCallback, useEffect, useRef, useState } from 'react';

import { flushOutbox, type FlushResult, type SalePoster } from '../lib/salesOutbox';
import { useOnlineStatus } from './useOnlineStatus';

/**
 * Vacía el outbox de ventas POS al recuperar la conexión — CTF-008 Nivel 2.
 *
 * Reintenta las ventas encoladas (ver `lib/salesOutbox`) cuando el navegador
 * pasa a `online` (y una vez al montar si ya hay conexión). El reenvío usa la
 * clave de idempotencia estable de cada venta, así que repetir el flush nunca
 * duplica (garantía del backend, ADR-012). Un flush no se solapa con otro.
 *
 * `poster` es la función que efectivamente reenvía la venta; cuando es `null`
 * (p. ej. usuario sin sesión) el hook no hace nada. No está cableado al POS
 * todavía; es la pieza de reconexión que consumirá la pantalla del cajero.
 */
export interface UseOutboxFlush {
  flushing: boolean;
  lastResult: FlushResult | null;
  flushNow: () => Promise<FlushResult | null>;
}

export function useOutboxFlush(poster: SalePoster | null): UseOutboxFlush {
  const online = useOnlineStatus();
  const [flushing, setFlushing] = useState(false);
  const [lastResult, setLastResult] = useState<FlushResult | null>(null);
  const enCurso = useRef(false);

  const flushNow = useCallback(async (): Promise<FlushResult | null> => {
    if (!poster || enCurso.current) return null;
    enCurso.current = true;
    setFlushing(true);
    try {
      const res = await flushOutbox(poster);
      setLastResult(res);
      return res;
    } finally {
      enCurso.current = false;
      setFlushing(false);
    }
  }, [poster]);

  useEffect(() => {
    if (online && poster) {
      void flushNow();
    }
  }, [online, poster, flushNow]);

  return { flushing, lastResult, flushNow };
}
