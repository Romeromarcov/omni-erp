import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  clearOutbox,
  clearSyncedOutboxItems,
  discardOutboxItem,
  enqueueSale,
  flushOutbox,
  listOutboxItems,
  listPending,
  retryOutboxItem,
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

  it('guarda mapeo SINCRONIZADA tras 2xx y no reenvía en futuros flushes', async () => {
    await enqueueSale({ ...venta('S1'), folioProvisional: 'POS-S1' });
    const poster = vi.fn().mockResolvedValue({
      id_nota_venta: 'nv-srv-1',
      numero_nota: 'POS-srv-1',
      alerta_stock_negativo: true,
    });

    const r1 = await flushOutbox(poster);
    expect(r1.enviados).toBe(1);
    expect(r1.sincronizadas).toEqual([
      { idempotencyKey: 'S1', idNotaVenta: 'nv-srv-1', numeroNota: 'POS-srv-1', alertaStockNegativo: true },
    ]);

    const items = await listOutboxItems();
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      idempotencyKey: 'S1',
      estado: 'SINCRONIZADA',
      idNotaVenta: 'nv-srv-1',
      numeroNota: 'POS-srv-1',
      alertaStockNegativo: true,
    });

    // Segundo flush no vuelve a enviar la venta sincronizada.
    const r2 = await flushOutbox(poster);
    expect(r2).toMatchObject({ enviados: 0, rechazados: 0, pendientes: 0 });
    expect(poster).toHaveBeenCalledTimes(1);
  });

  it('422 REQUIERE_REVISION marca estado permanente sin reintento en bucle y soporta Reintentar / Descartar', async () => {
    await enqueueSale(venta('R1'));
    const err422 = new Error(JSON.stringify({ error: 'Stock insuficiente.', codigo: 'REQUIERE_REVISION' })) as Error & {
      status: number;
    };
    err422.status = 422;
    const poster = vi.fn().mockRejectedValueOnce(err422).mockResolvedValueOnce({
      id_nota_venta: 'nv-ok',
      numero_nota: 'POS-ok',
    });

    const r1 = await flushOutbox(poster);
    expect(r1).toMatchObject({ enviados: 0, rechazados: 1, pendientes: 0 });
    expect(r1.errores[0]).toMatchObject({
      idempotencyKey: 'R1',
      status: 422,
      codigo: 'REQUIERE_REVISION',
      mensaje: 'Stock insuficiente.',
    });

    // No se reintenta en un flush posterior mientras esté en REQUIERE_REVISION.
    await flushOutbox(poster);
    expect(poster).toHaveBeenCalledTimes(1);

    const items = await listOutboxItems();
    expect(items[0]).toMatchObject({
      estado: 'REQUIERE_REVISION',
      errorMensaje: 'Stock insuficiente.',
      errorCodigo: 'REQUIERE_REVISION',
      errorStatus: 422,
    });

    // Reintentar la vuelve a PENDIENTE y limpia errores.
    await retryOutboxItem('R1');
    expect((await listPending()).map((i) => i.idempotencyKey)).toEqual(['R1']);
    const r2 = await flushOutbox(poster);
    expect(r2.enviados).toBe(1);
    expect((await listOutboxItems())[0].estado).toBe('SINCRONIZADA');

    // clearSyncedOutboxItems y discardOutboxItem.
    await enqueueSale(venta('P2'));
    await clearSyncedOutboxItems();
    expect((await listOutboxItems()).map((i) => i.idempotencyKey)).toEqual(['P2']);
    await discardOutboxItem('P2');
    expect(await listOutboxItems()).toEqual([]);
  });

  it('enqueueSale deduplica por idempotencyKey', async () => {
    await enqueueSale(venta('DUP'));
    await enqueueSale(venta('DUP'));
    expect(await listPending()).toHaveLength(1);
  });

  it('preserva ventas encoladas concurrentemente mientras flushOutbox tiene un envío en vuelo', async () => {
    await enqueueSale(venta('V1'));

    let resolveV1!: (value: unknown) => void;
    const v1EnVuelo = new Promise((res) => {
      resolveV1 = res;
    });

    const poster = vi.fn().mockImplementation((_endpoint: string, _payload: unknown, key: string) => {
      if (key === 'V1') return v1EnVuelo;
      return Promise.resolve({ id_nota_venta: `srv-${key}`, numero_nota: `POS-${key}` });
    });

    const pFlush = flushOutbox(poster);
    await vi.waitFor(() => expect(poster).toHaveBeenCalledTimes(1));

    // Mientras V1 está en vuelo, el cajero emite V2 y la encola.
    await enqueueSale(venta('V2'));

    resolveV1({ id_nota_venta: 'srv-V1', numero_nota: 'POS-V1' });
    const res = await pFlush;

    expect(res).toMatchObject({ enviados: 2, rechazados: 0, pendientes: 0 });
    const items = await listOutboxItems();
    expect(items.map((i) => [i.idempotencyKey, i.estado])).toEqual([
      ['V1', 'SINCRONIZADA'],
      ['V2', 'SINCRONIZADA'],
    ]);
  });

  it('clearOutbox durante un envío en vuelo aborta el flush y no resucita ventas ni pisa una nueva sesión', async () => {
    await enqueueSale(venta('OLD-1'));

    let resolveOld!: (value: unknown) => void;
    const oldEnVuelo = new Promise((res) => {
      resolveOld = res;
    });
    const poster = vi.fn().mockImplementation(() => oldEnVuelo);

    const pFlush = flushOutbox(poster);
    await vi.waitFor(() => expect(poster).toHaveBeenCalledTimes(1));

    // Ocurre logout() → clearOutbox() y luego un nuevo tenant encola NEW-1 antes de que resuelva OLD-1.
    await clearOutbox();
    await enqueueSale(venta('NEW-1'));

    resolveOld({ id_nota_venta: 'srv-old', numero_nota: 'POS-OLD' });
    const res = await pFlush;

    expect(res).toMatchObject({ enviados: 0, rechazados: 0, pendientes: 0 });
    const items = await listOutboxItems();
    expect(items.map((i) => [i.idempotencyKey, i.estado])).toEqual([['NEW-1', 'PENDIENTE']]);
  });
});
