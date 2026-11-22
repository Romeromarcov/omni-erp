/**
 * Cliente del pull de deltas (CTF-008 N2) contra el endpoint real vía MSW.
 * Verifica el envío de query params, una página simple, y la paginación por
 * cursor (avance de `desde` + dedup del borde por PK).
 */
import { describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { apiUrl } from '../test/handlers';
import { pullDeltas, pullAllDeltas, pushOptimisticUpdate } from '../services/syncService';
import {
  clearSyncConflicts,
  enqueueSyncConflict,
  listSyncConflicts,
  retrySyncConflictWithServerCursor,
} from '../lib/syncConflictQueue';

describe('syncService.pullDeltas (MSW)', () => {
  it('envía entity/desde/limite y devuelve la página', async () => {
    let urlVista = '';
    server.use(
      http.get(apiUrl('/sync/pull/'), ({ request }) => {
        urlVista = request.url;
        return HttpResponse.json({
          entity: 'productos', server_time: '2026-06-18T10:00:00Z',
          count: 1, has_more: false,
          results: [{ id_producto: 'p1', activo: true, fecha_actualizacion: '2026-06-18T09:00:00Z' }],
        });
      }),
    );

    const resp = await pullDeltas('productos', { desde: '2026-06-01T00:00:00Z', limite: 100 });
    expect(resp.count).toBe(1);
    expect(resp.has_more).toBe(false);
    const u = new URL(urlVista);
    expect(u.searchParams.get('entity')).toBe('productos');
    expect(u.searchParams.get('desde')).toBe('2026-06-01T00:00:00Z');
    expect(u.searchParams.get('limite')).toBe('100');
  });
});

describe('syncService.pullAllDeltas (MSW)', () => {
  it('pagina por cursor hasta agotar has_more y deduplica el borde por PK', async () => {
    const cursores: (string | null)[] = [];
    server.use(
      http.get(apiUrl('/sync/pull/'), ({ request }) => {
        const desde = new URL(request.url).searchParams.get('desde');
        cursores.push(desde);
        if (!desde || desde < '2026-06-02T00:00:00Z') {
          // Página 1: borde p2@06-02 (se repetirá en la página 2 por el >= inclusivo).
          return HttpResponse.json({
            entity: 'productos', server_time: '2026-06-18T10:00:00Z',
            count: 2, has_more: true,
            results: [
              { id_producto: 'p1', activo: true, fecha_actualizacion: '2026-06-01T00:00:00Z' },
              { id_producto: 'p2', activo: true, fecha_actualizacion: '2026-06-02T00:00:00Z' },
            ],
          });
        }
        // Página 2: el borde p2 otra vez + p3; ya sin más páginas.
        return HttpResponse.json({
          entity: 'productos', server_time: '2026-06-18T10:05:00Z',
          count: 2, has_more: false,
          results: [
            { id_producto: 'p2', activo: true, fecha_actualizacion: '2026-06-02T00:00:00Z' },
            { id_producto: 'p3', activo: true, fecha_actualizacion: '2026-06-03T00:00:00Z' },
          ],
        });
      }),
    );

    const { records, serverTime } = await pullAllDeltas('productos');
    const ids = records.map((r) => r.id_producto).sort();
    expect(ids).toEqual(['p1', 'p2', 'p3']); // p2 deduplicado por PK
    expect(serverTime).toBe('2026-06-18T10:05:00Z');
    // La segunda llamada avanzó el cursor al máximo fecha de la página 1.
    expect(cursores[1]).toBe('2026-06-02T00:00:00Z');
  });

  it('una sola página sin has_more no vuelve a pedir', async () => {
    let llamadas = 0;
    server.use(
      http.get(apiUrl('/sync/pull/'), () => {
        llamadas++;
        return HttpResponse.json({
          entity: 'clientes', server_time: '2026-06-18T10:00:00Z',
          count: 0, has_more: false, results: [],
        });
      }),
    );
    const { records } = await pullAllDeltas('clientes');
    expect(records).toEqual([]);
    expect(llamadas).toBe(1);
  });
});

describe('syncService.pushOptimisticUpdate y cola de conflictos (MSW)', () => {
  it('retorna ok=true en 200 y envía Idempotency-Key', async () => {
    let seenIdem = '';
    server.use(
      http.post(apiUrl('/sync/push/'), async ({ request }) => {
        seenIdem = request.headers.get('Idempotency-Key') ?? '';
        const body = (await request.json()) as { id: string };
        return HttpResponse.json({
          entity: 'clientes',
          id: body.id,
          server_time: '2026-11-22T12:00:00Z',
          registro: {
            id_cliente: body.id,
            telefono: '0412-1112233',
            activo: true,
            fecha_actualizacion: '2026-11-22T12:00:00Z',
          },
        });
      }),
    );

    const res = await pushOptimisticUpdate(
      {
        entity: 'clientes',
        id: 'c-1',
        expected_fecha_actualizacion: '2026-11-22T10:00:00Z',
        cambios: { telefono: '0412-1112233' },
      },
      'key-sync-1',
    );
    expect(res.ok).toBe(true);
    expect(seenIdem).toBe('key-sync-1');
  });

  it('retorna ok=false con CONFLICTO_VERSION en 409 y permite reintentar con el cursor servidor', async () => {
    clearSyncConflicts();
    server.use(
      http.post(apiUrl('/sync/push/'), async ({ request }) => {
        const body = (await request.json()) as { expected_fecha_actualizacion: string };
        if (body.expected_fecha_actualizacion === '2026-11-22T10:00:00Z') {
          return HttpResponse.json(
            {
              error: 'El registro fue modificado en el servidor.',
              codigo: 'CONFLICTO_VERSION',
              entity: 'clientes',
              id: 'c-2',
              registro_servidor: {
                id_cliente: 'c-2',
                telefono: '0424-9990000',
                activo: true,
                fecha_actualizacion: '2026-11-22T11:30:00Z',
              },
            },
            { status: 409 },
          );
        }
        return HttpResponse.json({
          entity: 'clientes',
          id: 'c-2',
          server_time: '2026-11-22T12:05:00Z',
          registro: {
            id_cliente: 'c-2',
            telefono: '0414-5556666',
            activo: true,
            fecha_actualizacion: '2026-11-22T12:05:00Z',
          },
        });
      }),
    );

    const mutacion = {
      entity: 'clientes' as const,
      id: 'c-2',
      expected_fecha_actualizacion: '2026-11-22T10:00:00Z',
      cambios: { telefono: '0414-5556666' },
    };
    const r1 = await pushOptimisticUpdate(mutacion);
    expect(r1.ok).toBe(false);
    if (!r1.ok) {
      const queued = enqueueSyncConflict(mutacion, r1.conflicto);
      expect(listSyncConflicts()).toHaveLength(1);
      const r2 = await retrySyncConflictWithServerCursor(queued);
      expect(r2.ok).toBe(true);
      expect(listSyncConflicts()).toHaveLength(0);
    }
  });
});
