import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';

const hydrateSessionMock = vi.fn().mockResolvedValue(null);
const logoutSessionMock = vi.fn();

vi.mock('../services/auth', () => ({
  loginAndFetchUser: vi.fn(),
  hydrateSession: (...a: unknown[]) => hydrateSessionMock(...a),
  logoutSession: (...a: unknown[]) => logoutSessionMock(...a),
}));

import { AuthProvider, useAuth } from '../contexts/AuthContext';
import { enqueueSale, listOutboxItems, clearOutbox } from '../lib/salesOutbox';

function Probe() {
  const { logout, isLoading } = useAuth();
  return (
    <div>
      <span>{isLoading ? 'loading' : 'ready'}</span>
      <button data-testid="btn-logout" onClick={logout}>
        Logout
      </button>
    </div>
  );
}

describe('AuthContext logout purga outbox y caché POS (R-CODE-1)', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    localStorage.clear();
    await clearOutbox();
  });

  it('limpia el outbox offline y llaves POS de localStorage al cerrar sesión', async () => {
    await enqueueSale({
      idempotencyKey: 'venta-tenant-a',
      endpoint: '/sync/push/ventas/',
      payload: { client_uuid: 'venta-tenant-a' },
      createdAt: Date.now(),
    });
    localStorage.setItem('id_empresa', 'emp-a');
    localStorage.setItem('pos_cliente_mostrador_emp-a', 'cli-a');
    expect(await listOutboxItems()).toHaveLength(1);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await screen.findByText('ready');

    await act(async () => {
      screen.getByTestId('btn-logout').click();
    });

    await waitFor(async () => {
      expect(await listOutboxItems()).toEqual([]);
    });
    expect(logoutSessionMock).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('id_empresa')).toBeNull();
    expect(localStorage.getItem('pos_cliente_mostrador_emp-a')).toBeNull();
  });
});
