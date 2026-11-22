import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';

const loginAndFetchUserMock = vi.fn();
const hydrateSessionMock = vi.fn();
const hydrateSessionResultMock = vi.fn();
const logoutSessionMock = vi.fn();

vi.mock('../services/auth', () => ({
  loginAndFetchUser: (...a: unknown[]) => loginAndFetchUserMock(...a),
  hydrateSession: (...a: unknown[]) => hydrateSessionMock(...a),
  hydrateSessionResult: (...a: unknown[]) => hydrateSessionResultMock(...a),
  logoutSession: (...a: unknown[]) => logoutSessionMock(...a),
}));

import { AuthProvider, useAuth } from '../contexts/AuthContext';
import { enqueueSale, listOutboxItems, clearOutbox } from '../lib/salesOutbox';

const USER_A = {
  id: 'user-a',
  username: 'cajero_a',
  empresas: [{ id_empresa: 'emp-a', nombre_legal: 'Alpha' }],
  sucursales: [{ id_sucursal: 'suc-a' }],
};

const USER_B = {
  id: 'user-b',
  username: 'cajero_b',
  empresas: [{ id_empresa: 'emp-b', nombre_legal: 'Beta' }],
  sucursales: [{ id_sucursal: 'suc-b' }],
};

function Probe() {
  const { user, logout, login, refreshUser, isLoading } = useAuth();
  return (
    <div>
      <span data-testid="auth-state">{isLoading ? 'loading' : user ? `user:${user.username}` : 'anon'}</span>
      <button data-testid="btn-logout" onClick={logout}>
        Logout
      </button>
      <button data-testid="btn-login-a" onClick={() => void login('cajero_a', 'pw')}>
        Login A
      </button>
      <button data-testid="btn-login-b" onClick={() => void login('cajero_b', 'pw')}>
        Login B
      </button>
      <button data-testid="btn-refresh" onClick={() => void refreshUser()}>
        Refresh
      </button>
    </div>
  );
}

async function seedTenantAOutbox(key = 'venta-tenant-a') {
  localStorage.setItem('pos_auth_scope', 'user-a:emp-a');
  localStorage.setItem('id_empresa', 'emp-a');
  localStorage.setItem('pos_cliente_mostrador_emp-a', 'cli-a');
  localStorage.setItem('pos_almacen_emp-a', 'alm-a');
  await enqueueSale({
    idempotencyKey: key,
    endpoint: '/sync/push/ventas/',
    payload: { client_uuid: key },
    createdAt: Date.now(),
  });
}

describe('AuthContext purga e isolamento de outbox ante logout, rechazo 401/403 vs fallo transitorio offline/5xx', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    localStorage.clear();
    await clearOutbox();
    hydrateSessionMock.mockResolvedValue(null);
    hydrateSessionResultMock.mockResolvedValue({ status: 'rejected' });
  });

  it('limpia el outbox offline y llaves POS de localStorage al cerrar sesión', async () => {
    hydrateSessionResultMock.mockResolvedValueOnce({ status: 'ok', usuario: USER_A });
    await seedTenantAOutbox();

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('auth-state').textContent).toBe('user:cajero_a'));
    expect(await listOutboxItems()).toHaveLength(1);

    await act(async () => {
      screen.getByTestId('btn-logout').click();
    });

    await waitFor(async () => {
      expect(await listOutboxItems()).toEqual([]);
    });
    expect(logoutSessionMock).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('id_empresa')).toBeNull();
    expect(localStorage.getItem('pos_auth_scope')).toBeNull();
    expect(localStorage.getItem('pos_cliente_mostrador_emp-a')).toBeNull();
    expect(localStorage.getItem('pos_almacen_emp-a')).toBeNull();
  });

  it('rechazo confirmado (401/403) durante hydrateSession sí purga outbox y pos_auth_scope', async () => {
    hydrateSessionResultMock.mockResolvedValueOnce({ status: 'rejected' });
    await seedTenantAOutbox('venta-rechazada-401');

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('auth-state').textContent).toBe('anon'));

    await waitFor(async () => {
      expect(await listOutboxItems()).toEqual([]);
    });
    expect(localStorage.getItem('id_empresa')).toBeNull();
    expect(localStorage.getItem('pos_auth_scope')).toBeNull();
    expect(localStorage.getItem('pos_cliente_mostrador_emp-a')).toBeNull();
    expect(localStorage.getItem('pos_almacen_emp-a')).toBeNull();
  });

  it('recarga offline / error 502 (transient_error) preserva outbox y pos_auth_scope; al volver red y loguearse mismo user:empresa las conserva', async () => {
    hydrateSessionResultMock.mockResolvedValueOnce({ status: 'transient_error' });
    loginAndFetchUserMock.mockResolvedValueOnce({ token: 'tok-a', usuario: USER_A });
    await seedTenantAOutbox('venta-offline-tras-f5');

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('auth-state').textContent).toBe('anon'));

    // Tras F5 offline o 502, las ventas offline y pos_auth_scope siguen intactos.
    expect((await listOutboxItems()).map((i) => i.idempotencyKey)).toEqual(['venta-offline-tras-f5']);
    expect(localStorage.getItem('pos_auth_scope')).toBe('user-a:emp-a');
    expect(localStorage.getItem('pos_cliente_mostrador_emp-a')).toBe('cli-a');
    expect(logoutSessionMock).not.toHaveBeenCalled();

    // Al volver la red e iniciar sesión el MISMO usuario/empresa, su outbox permanece listo para sincronizar.
    await act(async () => {
      screen.getByTestId('btn-login-a').click();
    });
    await waitFor(() => expect(screen.getByTestId('auth-state').textContent).toBe('user:cajero_a'));
    expect((await listOutboxItems()).map((i) => i.idempotencyKey)).toEqual(['venta-offline-tras-f5']);
  });

  it('recarga offline preserva outbox pero si luego inicia sesión OTRO usuario/empresa lo purga antes de exponer nada', async () => {
    hydrateSessionResultMock.mockResolvedValueOnce({ status: 'transient_error' });
    loginAndFetchUserMock.mockResolvedValueOnce({ token: 'tok-b', usuario: USER_B });
    await seedTenantAOutbox('venta-tenant-a-tras-f5');

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('auth-state').textContent).toBe('anon'));
    expect(await listOutboxItems()).toHaveLength(1);

    await act(async () => {
      screen.getByTestId('btn-login-b').click();
    });

    await waitFor(async () => {
      expect(await listOutboxItems()).toEqual([]);
    });
    expect(localStorage.getItem('id_empresa')).toBe('emp-b');
    expect(localStorage.getItem('pos_auth_scope')).toBe('user-b:emp-b');
    expect(localStorage.getItem('pos_cliente_mostrador_emp-a')).toBeNull();
    expect(localStorage.getItem('pos_almacen_emp-a')).toBeNull();
  });

  it('refreshUser ante 503/red (transient_error) no purga outbox, pero ante rejected sí hace logout', async () => {
    hydrateSessionResultMock
      .mockResolvedValueOnce({ status: 'ok', usuario: USER_A })
      .mockResolvedValueOnce({ status: 'transient_error' })
      .mockResolvedValueOnce({ status: 'rejected' });
    await seedTenantAOutbox('venta-refresh-503');

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('auth-state').textContent).toBe('user:cajero_a'));

    // Primer refresh falla por red/503 → NO llama logout ni borra outbox.
    await act(async () => {
      screen.getByTestId('btn-refresh').click();
    });
    expect(logoutSessionMock).not.toHaveBeenCalled();
    expect((await listOutboxItems()).map((i) => i.idempotencyKey)).toEqual(['venta-refresh-503']);

    // Segundo refresh sufre rechazo 401/403 confirmado → sí hace logout y purga outbox.
    await act(async () => {
      screen.getByTestId('btn-refresh').click();
    });
    await waitFor(async () => {
      expect(await listOutboxItems()).toEqual([]);
    });
    expect(logoutSessionMock).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('auth-state').textContent).toBe('anon');
  });
});
