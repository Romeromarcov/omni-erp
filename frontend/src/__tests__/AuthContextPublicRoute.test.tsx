import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';

const hydrateSessionMock = vi.fn();
const hydrateSessionResultMock = vi.fn();
const logoutSessionMock = vi.fn();
const loginAndFetchUserMock = vi.fn();

vi.mock('../services/auth', () => ({
  hydrateSession: (...a: unknown[]) => hydrateSessionMock(...a),
  hydrateSessionResult: (...a: unknown[]) => hydrateSessionResultMock(...a),
  logoutSession: (...a: unknown[]) => logoutSessionMock(...a),
  loginAndFetchUser: (...a: unknown[]) => loginAndFetchUserMock(...a),
}));

import * as apiModule from '../services/api';
import { AuthProvider, useAuth } from '../contexts/AuthContext';

function AuthProbe() {
  const { isLoading, token } = useAuth();
  return (
    <span data-testid="auth-probe">
      {isLoading ? 'loading' : token ? 'authed' : 'anon'}
    </span>
  );
}

describe('AuthProvider en rutas públicas Connect (/c/:slug)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.pushState({}, '', '/');
  });

  it('no dispara hydrateSessionResult ni redirige a /login en pathname /c/:slug', async () => {
    window.history.pushState({}, '', '/c/juan-perez');
    let registeredUnauthorized: (() => void) | null = null;
    vi.spyOn(apiModule, 'setUnauthorizedHandler').mockImplementation((handler) => {
      if (handler) registeredUnauthorized = handler;
    });

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-probe').textContent).toBe('anon');
    });
    expect(hydrateSessionResultMock).not.toHaveBeenCalled();
    expect(hydrateSessionMock).not.toHaveBeenCalled();

    expect(registeredUnauthorized).not.toBeNull();
    await act(async () => {
      registeredUnauthorized!();
    });
    expect(window.location.pathname).toBe('/c/juan-perez');
  });

  it('no dispara hydrateSessionResult ni redirige en HashRouter (#/c/:slug)', async () => {
    window.history.pushState({}, '', '/#/c/ana-gomez');
    let registeredUnauthorized: (() => void) | null = null;
    vi.spyOn(apiModule, 'setUnauthorizedHandler').mockImplementation((handler) => {
      if (handler) registeredUnauthorized = handler;
    });

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-probe').textContent).toBe('anon');
    });
    expect(hydrateSessionResultMock).not.toHaveBeenCalled();
    expect(hydrateSessionMock).not.toHaveBeenCalled();

    expect(registeredUnauthorized).not.toBeNull();
    await act(async () => {
      registeredUnauthorized!();
    });
    expect(window.location.hash).toBe('#/c/ana-gomez');
  });
});
