import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  clearOutbox,
  enqueueSale,
  flushOutbox,
  listPending,
  type OutboxSale,
} from '../salesOutbox';

function venta(key: string): OutboxSale {
  return {
    idempotencyKey: key,
    endpoint: '/ventas/notas-venta/',
    payload: { numero_nota: key },
    createdAt: Date.now(),
  };
}

/** Error HTTP con `.status`, como el que arma services/api.ts (buildError). */
function httpError(status: number): Error {
  const e = new Error(`Error ${status}`) as Error & { status: number };
  e.status = status;
  return e;
}

describe('salesOutbox', () => {
  beforeEach(async () => {
    await clearOutbox();
  });

  it('encola y lista en orden FIFO', async () => {
    await enqueueSale(venta('A'));
    await enqueueSale(venta('B'));
    const pend = await listPending();
    expect(pend.map((v) => v.idempotencyKey)).toEqual(['A', 'B']);
  });

  it('flush exitoso reenvía con la clave estable y vacía la cola', async () => {
    await enqueueSale(venta('A'));
    const poster = vi.fn().mockResolvedValue({ id_nota_venta: 'srv-1' });

    const r = await flushOutbox(poster);

    expect(r).toMatchObject({ enviados: 1, rechazados: 0, pendientes: 0 });
    expect(poster).toHaveBeenCalledWith('/ventas/notas-venta/', { numero_nota: 'A' }, 'A');
    expect(await listPending()).toEqual([]);
  });

  it('error de red (sin status) deja la venta pendiente para reintentar', async () => {
    await enqueueSale(venta('A'));
    const poster = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

    const r = await flushOutbox(poster);

    expect(r.enviados).toBe(0);
    expect(r.pendientes).toBe(1);
    expect((await listPending()).map((v) => v.idempotencyKey)).toEqual(['A']);
  });

  it('un 4xx permanente descarta la venta y la reporta', async () => {
    await enqueueSale(venta('A'));
    const poster = vi.fn().mockRejectedValue(httpError(422));

    const r = await flushOutbox(poster);

    expect(r).toMatchObject({ enviados: 0, rechazados: 1, pendientes: 0 });
    expect(r.errores[0]).toMatchObject({ idempotencyKey: 'A', status: 422 });
    expect(await listPending()).toEqual([]);
  });

  it('un error transitorio detiene el flush y conserva el resto (orden)', async () => {
    await enqueueSale(venta('A'));
    await enqueueSale(venta('B'));
    await enqueueSale(venta('C'));
    // A ok, B error de red → C no se intenta.
    const poster = vi
      .fn()
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new TypeError('offline'));

    const r = await flushOutbox(poster);

    expect(r.enviados).toBe(1);
    expect(r.pendientes).toBe(2);
    expect(poster).toHaveBeenCalledTimes(2); // C no se intentó
    expect((await listPending()).map((v) => v.idempotencyKey)).toEqual(['B', 'C']);
  });

  it('5xx se trata como transitorio (no se descarta)', async () => {
    await enqueueSale(venta('A'));
    const poster = vi.fn().mockRejectedValue(httpError(503));

    const r = await flushOutbox(poster);

    expect(r.rechazados).toBe(0);
    expect(r.pendientes).toBe(1);
  });

  it('mezcla: 4xx descarta y sigue con la siguiente', async () => {
    await enqueueSale(venta('A'));
    await enqueueSale(venta('B'));
    const poster = vi
      .fn()
      .mockRejectedValueOnce(httpError(400)) // A permanente → descarta, sigue
      .mockResolvedValueOnce({}); // B ok

    const r = await flushOutbox(poster);

    expect(r).toMatchObject({ enviados: 1, rechazados: 1, pendientes: 0 });
    expect(await listPending()).toEqual([]);
  });
});
