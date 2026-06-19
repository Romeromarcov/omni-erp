import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { clearOutbox, enqueueSale, listPending } from '../../lib/salesOutbox';
import { useOutboxFlush } from '../useOutboxFlush';

function setOnline(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { value, configurable: true });
}

beforeEach(async () => {
  await clearOutbox();
  setOnline(true);
});

afterEach(() => {
  setOnline(true);
});

const venta = {
  idempotencyKey: 'k1',
  endpoint: '/ventas/notas-venta/',
  payload: { numero_nota: 'NV-1' },
  createdAt: 1,
};

describe('useOutboxFlush', () => {
  it('vacía el outbox al montar si hay conexión y poster', async () => {
    await enqueueSale(venta);
    const poster = vi.fn().mockResolvedValue({ id: 'srv-1' });

    renderHook(() => useOutboxFlush(poster));

    await waitFor(() => expect(poster).toHaveBeenCalledTimes(1));
    expect(poster).toHaveBeenCalledWith('/ventas/notas-venta/', { numero_nota: 'NV-1' }, 'k1');
    expect(await listPending()).toHaveLength(0);
  });

  it('no hace nada cuando el poster es null', async () => {
    await enqueueSale(venta);
    renderHook(() => useOutboxFlush(null));
    // Da una vuelta al event loop; no debe vaciar la cola.
    await new Promise((r) => setTimeout(r, 0));
    expect(await listPending()).toHaveLength(1);
  });

  it('flushNow reenvía manualmente y expone el resultado', async () => {
    await enqueueSale(venta);
    const poster = vi.fn().mockResolvedValue({ ok: true });
    const { result } = renderHook(() => useOutboxFlush(poster));

    await waitFor(() => expect(result.current.lastResult).not.toBeNull());
    expect(result.current.lastResult?.enviados).toBe(1);
  });

  it('reenvía al pasar de offline a online', async () => {
    setOnline(false);
    await enqueueSale(venta);
    const poster = vi.fn().mockResolvedValue({});

    renderHook(() => useOutboxFlush(poster));
    // Offline al montar: no reenvía.
    await new Promise((r) => setTimeout(r, 0));
    expect(poster).not.toHaveBeenCalled();

    // Vuelve la conexión.
    setOnline(true);
    window.dispatchEvent(new Event('online'));
    await waitFor(() => expect(poster).toHaveBeenCalledTimes(1));
  });
});
