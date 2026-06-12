/**
 * Offline Nivel 1 — banner global online/offline + badge "datos sin actualizar".
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import OfflineBanner from '../components/layout/OfflineBanner';

function setNavigatorOnline(value: boolean) {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(value);
}

function renderBanner() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OfflineBanner />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('OfflineBanner', () => {
  it('online: no muestra ningún aviso', () => {
    setNavigatorOnline(true);
    renderBanner();
    expect(screen.queryByText('Sin conexión — mostrando datos guardados')).not.toBeInTheDocument();
    expect(screen.queryByText('Conexión restablecida — sincronizando…')).not.toBeInTheDocument();
  });

  it('offline: muestra el banner y el badge de datos en caché', () => {
    setNavigatorOnline(false);
    renderBanner();
    expect(screen.getByText('Sin conexión — mostrando datos guardados')).toBeInTheDocument();
    expect(screen.getByText('Datos sin actualizar')).toBeInTheDocument();
  });

  it('al volver la red muestra el aviso de sincronización y lo oculta después', async () => {
    setNavigatorOnline(false);
    renderBanner();
    expect(screen.getByText('Sin conexión — mostrando datos guardados')).toBeInTheDocument();

    act(() => {
      setNavigatorOnline(true);
      window.dispatchEvent(new Event('online'));
    });

    expect(screen.getByText('Conexión restablecida — sincronizando…')).toBeInTheDocument();

    // El aviso desaparece solo tras RESTORED_BANNER_MS.
    await waitFor(
      () =>
        expect(
          screen.queryByText('Conexión restablecida — sincronizando…'),
        ).not.toBeInTheDocument(),
      { timeout: 6000 },
    );
  }, 10_000);
});
