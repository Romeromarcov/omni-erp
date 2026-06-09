import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  setAccessToken,
  getAccessToken,
  clearAccessToken,
  setUnauthorizedHandler,
  get,
  fetchText,
  streamSSE,
} from '../services/api';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function textResponse(body: string, status = 200): Response {
  return new Response(body, { status, headers: { 'Content-Type': 'text/plain' } });
}

function sseResponse(lines: string[]): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const enc = new TextEncoder();
      for (const l of lines) controller.enqueue(enc.encode(l));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

describe('api access token store', () => {
  beforeEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
    vi.restoreAllMocks();
  });
  afterEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
  });

  it('stores and clears the access token in memory', () => {
    expect(getAccessToken()).toBeNull();
    setAccessToken('abc');
    expect(getAccessToken()).toBe('abc');
    clearAccessToken();
    expect(getAccessToken()).toBeNull();
  });

  it('attaches Authorization from the in-memory token, never localStorage', async () => {
    localStorage.setItem('token', 'LEGACY-SHOULD-BE-IGNORED');
    setAccessToken('mem-token');
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await get('/some/endpoint/');

    const [, init] = fetchMock.mock.calls[0];
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer mem-token');
    expect(init.credentials).toBe('include');
    localStorage.removeItem('token');
  });

  it('does NOT attach Authorization to credential endpoints (login/logout/token)', async () => {
    setAccessToken('mem-token');
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ access: 'x' }));
    vi.stubGlobal('fetch', fetchMock);

    await get('/auth/token/verify/');

    const [, init] = fetchMock.mock.calls[0];
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it('DOES attach Authorization to /auth/profile/ (needs the bearer — fixes 401 logout loop)', async () => {
    setAccessToken('mem-token');
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: '1' }));
    vi.stubGlobal('fetch', fetchMock);

    await get('/auth/profile/');

    const [, init] = fetchMock.mock.calls[0];
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer mem-token');
  });
});

describe('api 401 refresh + retry (FE-HIGH-11)', () => {
  beforeEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
    vi.restoreAllMocks();
  });
  afterEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
  });

  it('refreshes once on 401 then retries the original request with the new token', async () => {
    setAccessToken('old');
    const calls: Array<{ url: string; auth?: string }> = [];
    const fetchMock = vi.fn().mockImplementation((url: string, init: RequestInit) => {
      const auth = new Headers(init.headers).get('Authorization') ?? undefined;
      calls.push({ url, auth: auth ?? undefined });
      if (url.includes('/auth/token/refresh/')) {
        return Promise.resolve(jsonResponse({ access: 'new' }));
      }
      // First protected call (old token) → 401; retry (new token) → 200.
      if (auth === 'Bearer old') return Promise.resolve(jsonResponse({ detail: 'expired' }, 401));
      return Promise.resolve(jsonResponse({ ok: true }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await get<{ ok: boolean }>('/protected/');
    expect(result).toEqual({ ok: true });
    expect(getAccessToken()).toBe('new');
    // original(401) + refresh + retry(200) = 3 calls
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(calls[2].auth).toBe('Bearer new');
  });

  it('signals logout when refresh fails', async () => {
    setAccessToken('old');
    const onUnauth = vi.fn();
    setUnauthorizedHandler(onUnauth);
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/token/refresh/')) {
        return Promise.resolve(jsonResponse({ detail: 'no cookie' }, 401));
      }
      return Promise.resolve(jsonResponse({ detail: 'expired' }, 401));
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(get('/protected/')).rejects.toThrow(/Sesión expirada/);
    expect(onUnauth).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
  });

  it('guards concurrent 401s with a single shared refresh', async () => {
    setAccessToken('old');
    let refreshCount = 0;
    const fetchMock = vi.fn().mockImplementation((url: string, init: RequestInit) => {
      const auth = new Headers(init.headers).get('Authorization') ?? undefined;
      if (url.includes('/auth/token/refresh/')) {
        refreshCount += 1;
        return new Promise((resolve) =>
          setTimeout(() => resolve(jsonResponse({ access: 'new' })), 10),
        );
      }
      if (auth === 'Bearer old') return Promise.resolve(jsonResponse({ detail: 'expired' }, 401));
      return Promise.resolve(jsonResponse({ ok: true }));
    });
    vi.stubGlobal('fetch', fetchMock);

    await Promise.all([get('/a/'), get('/b/'), get('/c/')]);
    expect(refreshCount).toBe(1);
  });
});

describe('api fetchText / streamSSE (FE-HIGH-14)', () => {
  beforeEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
    vi.restoreAllMocks();
  });
  afterEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
  });

  it('fetchText returns the raw text body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(textResponse('a|b|c'));
    vi.stubGlobal('fetch', fetchMock);
    const txt = await fetchText('/fiscal/libro-ventas/');
    expect(txt).toBe('a|b|c');
  });

  it('streamSSE parses data lines and stops on [DONE]', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse(['data: {"text":"hola"}\n', 'data: {"text":" mundo"}\n', 'data: [DONE]\n']),
    );
    vi.stubGlobal('fetch', fetchMock);

    const chunks: string[] = [];
    await streamSSE('/agentes/chat/', (e) => {
      if (e.text) chunks.push(e.text as string);
    }, { method: 'POST', body: '{}' });

    expect(chunks.join('')).toBe('hola mundo');
  });
});
