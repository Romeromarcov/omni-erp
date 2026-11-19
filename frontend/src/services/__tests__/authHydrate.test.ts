import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetcherMock = vi.fn();
const getMock = vi.fn();
const setAccessTokenMock = vi.fn();
const clearAccessTokenMock = vi.fn();

vi.mock('../api', () => ({
  post: vi.fn(),
  fetcher: (...a: unknown[]) => fetcherMock(...a),
  get: (...a: unknown[]) => getMock(...a),
  setAccessToken: (...a: unknown[]) => setAccessTokenMock(...a),
  clearAccessToken: (...a: unknown[]) => clearAccessTokenMock(...a),
}));

import { hydrateSession, hydrateSessionResult } from '../auth';

function httpError(status: number, message = `HTTP ${status}`): Error & { status: number } {
  const err = new Error(message) as Error & { status: number };
  err.status = status;
  return err;
}

describe('hydrateSessionResult distingue rechazos 401/403/400 vs fallos transitorios offline/5xx', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('retorna ok cuando refresh y profile responden correctamente', async () => {
    const usuario = { id: 'u-1', username: 'cajero' };
    fetcherMock.mockResolvedValueOnce({ access: 'tok-1' });
    getMock.mockResolvedValueOnce(usuario).mockResolvedValueOnce([]);

    await expect(hydrateSessionResult()).resolves.toEqual({ status: 'ok', usuario });
    expect(setAccessTokenMock).toHaveBeenCalledWith('tok-1');
  });

  it('retorna rejected ante 401, 403, 400 o refresh sin access token', async () => {
    fetcherMock.mockResolvedValueOnce({});
    expect(await hydrateSessionResult()).toEqual({ status: 'rejected' });

    fetcherMock.mockRejectedValueOnce(httpError(401));
    expect(await hydrateSessionResult()).toEqual({ status: 'rejected' });

    fetcherMock.mockRejectedValueOnce(httpError(403));
    expect(await hydrateSessionResult()).toEqual({ status: 'rejected' });

    fetcherMock.mockRejectedValueOnce(httpError(400));
    expect(await hydrateSessionResult()).toEqual({ status: 'rejected' });

    // /auth/profile/ 401 en api.ts arroja Error('Sesión expirada. Redirigiendo al login...') sin .status
    fetcherMock.mockResolvedValueOnce({ access: 'tok-1' });
    getMock.mockRejectedValueOnce(new Error('Sesión expirada. Redirigiendo al login...'));
    expect(await hydrateSession()).toBeNull();
  });

  it('retorna transient_error ante TypeError de red, AbortError y errores 502/503', async () => {
    fetcherMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    expect(await hydrateSessionResult()).toEqual({ status: 'transient_error' });

    fetcherMock.mockRejectedValueOnce(new DOMException('The user aborted a request.', 'AbortError'));
    expect(await hydrateSessionResult()).toEqual({ status: 'transient_error' });

    fetcherMock.mockRejectedValueOnce(httpError(502));
    expect(await hydrateSessionResult()).toEqual({ status: 'transient_error' });

    fetcherMock.mockResolvedValueOnce({ access: 'tok-1' });
    getMock.mockRejectedValueOnce(httpError(503));
    expect(await hydrateSessionResult()).toEqual({ status: 'transient_error' });
    expect(clearAccessTokenMock).toHaveBeenCalled();
  });
});
