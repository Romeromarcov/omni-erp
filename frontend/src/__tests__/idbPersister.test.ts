/**
 * Offline Nivel 1 "réplica local" (CTF-008): el caché de TanStack Query se
 * persiste y rehidrata vía el persister de IndexedDB (en jsdom, sin IndexedDB,
 * cae al almacén en memoria — misma interfaz AsyncStorage), y se purga en el
 * logout para no filtrar datos entre usuarios/tenants.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import {
  persistQueryClientSave,
  persistQueryClientRestore,
} from '@tanstack/react-query-persist-client';
import { idbPersister, clearPersistedQueryCache } from '../lib/idbPersister';

const BUSTER = 'test';
const MAX_AGE = 1000 * 60 * 60 * 24;

function clienteConDato() {
  const qc = new QueryClient({ defaultOptions: { queries: { gcTime: MAX_AGE } } });
  qc.setQueryData(['clientes'], [{ id: '1', nombre: 'Acme' }]);
  return qc;
}

describe('idbPersister — réplica local del caché', () => {
  beforeEach(async () => {
    await clearPersistedQueryCache();
  });

  it('persiste y rehidrata el caché en un cliente nuevo (sobrevive a un reload)', async () => {
    const origen = clienteConDato();
    await persistQueryClientSave({ queryClient: origen, persister: idbPersister, buster: BUSTER });

    const rehidratado = new QueryClient({ defaultOptions: { queries: { gcTime: MAX_AGE } } });
    await persistQueryClientRestore({
      queryClient: rehidratado,
      persister: idbPersister,
      maxAge: MAX_AGE,
      buster: BUSTER,
    });

    expect(rehidratado.getQueryData(['clientes'])).toEqual([{ id: '1', nombre: 'Acme' }]);
  });

  it('un buster distinto descarta la réplica (deploy con forma de datos incompatible)', async () => {
    const origen = clienteConDato();
    await persistQueryClientSave({ queryClient: origen, persister: idbPersister, buster: 'v1' });

    const rehidratado = new QueryClient();
    await persistQueryClientRestore({
      queryClient: rehidratado,
      persister: idbPersister,
      maxAge: MAX_AGE,
      buster: 'v2',
    });

    expect(rehidratado.getQueryData(['clientes'])).toBeUndefined();
  });

  it('clearPersistedQueryCache borra la réplica (logout en dispositivo compartido)', async () => {
    const origen = clienteConDato();
    await persistQueryClientSave({ queryClient: origen, persister: idbPersister, buster: BUSTER });

    await clearPersistedQueryCache();

    const rehidratado = new QueryClient();
    await persistQueryClientRestore({
      queryClient: rehidratado,
      persister: idbPersister,
      maxAge: MAX_AGE,
      buster: BUSTER,
    });
    expect(rehidratado.getQueryData(['clientes'])).toBeUndefined();
  });

  it('clearPersistedQueryCache nunca lanza (best-effort, no bloquea el logout)', async () => {
    await expect(clearPersistedQueryCache()).resolves.toBeUndefined();
  });
});
