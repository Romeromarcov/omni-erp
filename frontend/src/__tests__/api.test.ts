import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  setAccessToken,
  getAccessToken,
  clearAccessToken,
  setUnauthorizedHandler,
  get,
  post,
  patch,
  put,
  del,
  fetchText,
  fetchBlob,
  streamSSE,
  API_URL,
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
      // eslint-disable-next-line security/detect-possible-timing-attacks -- FP: comparación dentro de un mock de fetch de tests; no hay secreto real ni canal de timing observable
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
      // eslint-disable-next-line security/detect-possible-timing-attacks -- FP: comparación dentro de un mock de fetch de tests; no hay secreto real ni canal de timing observable
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

  it('fetchText lanza «Sesión expirada» cuando el 401 persiste tras el refresh', async () => {
    setUnauthorizedHandler(vi.fn());
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/token/refresh/')) {
        return Promise.resolve(jsonResponse({ detail: 'no cookie' }, 401));
      }
      return Promise.resolve(textResponse('expired', 401));
    });
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchText('/fiscal/libro-ventas/')).rejects.toThrow(/Sesión expirada/);
  });

  it('fetchText construye el error legible cuando el servidor responde HTML', async () => {
    setUnauthorizedHandler(vi.fn());
    const fetchMock = vi
      .fn()
      .mockResolvedValue(textResponse('<!DOCTYPE html><html><body>boom</body></html>', 500));
    vi.stubGlobal('fetch', fetchMock);

    const err = await fetchText('/fiscal/libro-ventas/').catch((e: Error) => e);
    expect(err).toBeInstanceOf(Error);
    const parsed = JSON.parse((err as Error).message) as { error: string; details: string };
    expect(parsed.error).toMatch(/respuesta HTML en lugar de JSON/);
    expect(parsed.details).toContain('Status: 500');
  });

  it('fetchText envuelve el texto plano de error que no es JSON', async () => {
    setUnauthorizedHandler(vi.fn());
    const fetchMock = vi.fn().mockResolvedValue(textResponse('falla simple', 500));
    vi.stubGlobal('fetch', fetchMock);

    const err = await fetchText('/x/').catch((e: Error) => e);
    expect(JSON.parse((err as Error).message)).toEqual({ error: 'falla simple' });
  });

  it('fetchBlob devuelve el blob del cuerpo', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response('PDFDATA', { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);
    const blob = await fetchBlob('/reportes/pdf/');
    expect(await blob.text()).toBe('PDFDATA');
  });

  it('fetchBlob lanza «Sesión expirada» en 401 persistente', async () => {
    setUnauthorizedHandler(vi.fn());
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/token/refresh/')) {
        return Promise.resolve(jsonResponse({}, 401));
      }
      return Promise.resolve(jsonResponse({ detail: 'expired' }, 401));
    });
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchBlob('/reportes/pdf/')).rejects.toThrow(/Sesión expirada/);
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

  it('streamSSE ignora líneas que no son data y fragmentos JSON inválidos, y termina sin [DONE]', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([
        'event: ping\n',
        'data: {esto no es json}\n',
        'data: {"text":"ok"}\n',
        // sin [DONE]: el stream termina al cerrarse el reader
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    const chunks: string[] = [];
    await streamSSE('/agentes/chat/', (e) => {
      if (e.text) chunks.push(e.text as string);
    });
    expect(chunks).toEqual(['ok']);
  });

  it('streamSSE lanza Error N en respuestas no-ok que no son 401', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: 'boom' }, 500));
    vi.stubGlobal('fetch', fetchMock);
    await expect(streamSSE('/agentes/chat/', () => {})).rejects.toThrow('Error 500');
  });

  it('streamSSE lanza «Sesión expirada» en 401 persistente', async () => {
    setUnauthorizedHandler(vi.fn());
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/token/refresh/')) {
        return Promise.resolve(jsonResponse({}, 401));
      }
      return Promise.resolve(jsonResponse({ detail: 'expired' }, 401));
    });
    vi.stubGlobal('fetch', fetchMock);
    await expect(streamSSE('/agentes/chat/', () => {})).rejects.toThrow(/Sesión expirada/);
  });
});

describe('api verbs (post/patch/put/del) y resolución de URL', () => {
  beforeEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
    vi.restoreAllMocks();
  });
  afterEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
  });

  it.each([
    ['POST', post] as const,
    ['PATCH', patch] as const,
    ['PUT', put] as const,
  ])('%s serializa el cuerpo JSON y usa el método correcto', async (method, verb) => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await verb('/x/', { a: 1 });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API_URL}/x/`);
    expect(init.method).toBe(method);
    expect(init.body).toBe(JSON.stringify({ a: 1 }));
  });

  it('del usa el método DELETE', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    await del('/x/1/');
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('DELETE');
  });

  it('pasa URLs absolutas sin prefijar API_URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    await get('https://externo.example.com/ping');
    expect(fetchMock.mock.calls[0][0]).toBe('https://externo.example.com/ping');
  });
});

describe('api refresh — ramas de fallo y combinación de señales', () => {
  beforeEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
    vi.restoreAllMocks();
  });
  afterEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
  });

  it('señala logout si el refresh responde 200 sin campo access', async () => {
    const onUnauth = vi.fn();
    setUnauthorizedHandler(onUnauth);
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/token/refresh/')) return Promise.resolve(jsonResponse({}));
      return Promise.resolve(jsonResponse({ detail: 'expired' }, 401));
    });
    vi.stubGlobal('fetch', fetchMock);
    await expect(get('/protected/')).rejects.toThrow(/Sesión expirada/);
    expect(onUnauth).toHaveBeenCalledTimes(1);
  });

  it('señala logout si la petición de refresh lanza (red caída)', async () => {
    const onUnauth = vi.fn();
    setUnauthorizedHandler(onUnauth);
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/token/refresh/')) return Promise.reject(new Error('network down'));
      return Promise.resolve(jsonResponse({ detail: 'expired' }, 401));
    });
    vi.stubGlobal('fetch', fetchMock);
    await expect(get('/protected/')).rejects.toThrow(/Sesión expirada/);
    expect(onUnauth).toHaveBeenCalledTimes(1);
  });

  it('señala logout si el retry tras un refresh exitoso sigue en 401', async () => {
    const onUnauth = vi.fn();
    setUnauthorizedHandler(onUnauth);
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/token/refresh/')) {
        return Promise.resolve(jsonResponse({ access: 'nuevo' }));
      }
      return Promise.resolve(jsonResponse({ detail: 'still expired' }, 401));
    });
    vi.stubGlobal('fetch', fetchMock);
    await expect(get('/protected/')).rejects.toThrow(/Sesión expirada/);
    expect(onUnauth).toHaveBeenCalledTimes(1);
  });

  it('combina la señal del caller con la del timeout sin AbortSignal.any (fallback)', async () => {
    const abortSignalAny = (AbortSignal as unknown as Record<string, unknown>).any;
    (AbortSignal as unknown as Record<string, unknown>).any = undefined;
    try {
      const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({ ok: true })));
      vi.stubGlobal('fetch', fetchMock);

      const controller = new AbortController();
      await get('/x/');
      await expect(fetchText('/y/', { signal: controller.signal })).resolves.toBeDefined();

      // Señal ya abortada: la señal combinada nace abortada.
      const aborted = new AbortController();
      aborted.abort();
      await fetchText('/z/', { signal: aborted.signal });
      const lastInit = fetchMock.mock.calls.at(-1)?.[1] as RequestInit;
      expect((lastInit.signal as AbortSignal).aborted).toBe(true);
    } finally {
      (AbortSignal as unknown as Record<string, unknown>).any = abortSignalAny;
    }
  });
});

describe('api error status (workstream F: 422 mapeo NOMINA vs 400 negocio)', () => {
  beforeEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
    vi.restoreAllMocks();
  });
  afterEach(() => {
    clearAccessToken();
    setUnauthorizedHandler(null);
  });

  it('adjunta status=422 al Error sin alterar el message JSON', async () => {
    const body = { error: 'Configure el Mapeo Contable antes de continuar (contabilidad activa, NOMINA)' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(body, 422)));

    const err = await post('/nomina/procesos-nomina/p1/procesar/', {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(Error);
    expect((err as Error & { status?: number }).status).toBe(422);
    expect(JSON.parse((err as Error).message)).toEqual(body);
  });

  it('adjunta status=400 a los errores de regla de negocio', async () => {
    const body = { error: 'El proceso está en estado COMPLETADO; solo se procesan procesos EN_PROCESO.' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(body, 400)));

    const err = await post('/nomina/procesos-nomina/p1/procesar/', {}).catch((e: unknown) => e);
    expect((err as Error & { status?: number }).status).toBe(400);
  });
});
