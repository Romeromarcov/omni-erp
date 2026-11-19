import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';

const loginAndFetchUserMock = vi.fn();
const hydrateSessionMock = vi.fn().mockResolvedValue(null);
const logoutSessionMock = vi.fn();

vi.mock('../services/auth', () => ({
  loginAndFetchUser: (...a: unknown[]) => loginAndFetchUserMock(...a),
  hydrateSession: (...a: unknown[]) => hydrateSessionMock(...a),
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
  const { logout, login, isLoading } = useAuth();
  return (
    <div>
      <span>{isLoading ? 'loading' : 'ready'}</span>
      <button data-testid="btn-logout" onClick={logout}>
        Logout
      </button>
      <button data-testid="btn-login-b" onClick={() => void login('cajero_b', 'pw')}>
        Login B
      </button>
    </div>
  );
}

describe('AuthContext purga outbox y caché POS en logout, fallo de rehidratación y cambio de tenant (R-CODE-1)', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    localStorage.clear();
    await clearOutbox();
    hydrateSessionMock.mockResolvedValue(null);
  });

  it('limpia el outbox offline y llaves POS de localStorage al cerrar sesión', async () => {
    hydrateSessionMock.mockResolvedValueOnce(USER_A);
    localStorage.setItem('pos_auth_scope', 'user-a:emp-a');
    localStorage.setItem('id_empresa', 'emp-a');
    localStorage.setItem('pos_cliente_mostrador_emp-a', 'cli-a');
    localStorage.setItem('pos_almacen_emp-a', 'alm-a');
    await enqueueSale({
      idempotencyKey: 'venta-tenant-a',
      endpoint: '/sync/push/ventas/',
      payload: { client_uuid: 'venta-tenant-a' },
      createdAt: Date.now(),
    });
    expect(await listOutboxItems()).toHaveLength(1);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await screen.findByText('ready');
    expect(await listOutboxItems()).toHaveLength(1);

    await act(async () => {
      screen.getByTestId('btn-logout').click();
    });

    await waitFor(async () => {
      expect(await listOutboxItems()).toEqual([]);
    });
    expect(logoutSessionMock).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('id_empresa')).toBeNull();
    expect(localStorage.getItem('pos_cliente_mostrador_emp-a')).toBeNull();
    expect(localStorage.getItem('pos_almacen_emp-a')).toBeNull();
  });

  it('purga outbox y caché local si hydrateSession falla al arrancar (token expirado/ausente)', async () => {
    hydrateSessionMock.mockResolvedValueOnce(null);
    await enqueueSale({
      idempotencyKey: 'venta-expirada',
      endpoint: '/sync/push/ventas/',
      payload: { client_uuid: 'venta-expirada' },
      createdAt: Date.now(),
    });
    localStorage.setItem('id_empresa', 'emp-a');
    localStorage.setItem('pos_cliente_mostrador_emp-a', 'cli-a');
    localStorage.setItem('pos_almacen_emp-a', 'alm-a');

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await screen.findByText('ready');

    await waitFor(async () => {
      expect(await listOutboxItems()).toEqual([]);
    });
    expect(localStorage.getItem('id_empresa')).toBeNull();
    expect(localStorage.getItem('pos_cliente_mostrador_emp-a')).toBeNull();
    expect(localStorage.getItem('pos_almacen_emp-a')).toBeNull();
  });

  it('purga outbox y caché del tenant anterior al completar login con otro usuario/empresa sin logout previo', async () => {
    hydrateSessionMock.mockResolvedValueOnce(USER_A);
    loginAndFetchUserMock.mockResolvedValueOnce({ token: 'tok-b', usuario: USER_B });
    await enqueueSale({
      idempotencyKey: 'venta-tenant-a-sin-logout',
      endpoint: '/sync/push/ventas/',
      payload: { client_uuid: 'venta-tenant-a-sin-logout' },
      createdAt: Date.now(),
    });
    localStorage.setItem('pos_cliente_mostrador_emp-a', 'cli-a');
    localStorage.setItem('pos_almacen_emp-a', 'alm-a');

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await screen.findByText('ready');
    expect(await listOutboxItems()).toHaveLength(1);

    await act(async () => {
      screen.getByTestId('btn-login-b').click();
    });

    await waitFor(async () => {
      expect(await listOutboxItems()).toEqual([]);
    });
    expect(localStorage.getItem('id_empresa')).toBe('emp-b');
    expect(localStorage.getItem('pos_cliente_mostrador_emp-a')).toBeNull();
    expect(localStorage.getItem('pos_almacen_emp-a')).toBeNull();
  });
});
