// FE-LOW-S2: el default a localhost solo es válido en desarrollo. En un build de
// producción sin VITE_API_URL configurada apuntaríamos a localhost (bug silente);
// por eso hacemos fail-fast al cargar el módulo. En dev/test mantenemos el fallback.
function resolveApiUrl(): string {
  const configured = import.meta.env.VITE_API_URL;
  if (configured) return configured;
  if (import.meta.env.PROD) {
    throw new Error(
      'VITE_API_URL no está definida en el build de producción. ' +
        'Configura VITE_API_URL (p. ej. https://api.midominio.com/api) antes de compilar.',
    );
  }
  return 'http://localhost:8000/api';
}

export const API_URL = resolveApiUrl();

// ── In-memory access token (FE-HIGH-13) ──────────────────────────────────────
// The access token lives ONLY in this module variable, never in localStorage.
// The refresh token is an httpOnly cookie managed by the backend.
let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function clearAccessToken(): void {
  accessToken = null;
}

// ── Unauthorized handler (wired by AuthContext) ───────────────────────────────
// When a refresh fails (or a retry still 401s) we clear the token and signal the
// app to drop to an unauthenticated state. AuthContext registers a handler; the
// default falls back to a hard redirect to /login.
type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler;
}

function signalLogout(): void {
  clearAccessToken();
  if (onUnauthorized) {
    onUnauthorized();
  } else if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
    window.location.href = '/login';
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function isAuthEndpoint(endpoint: string): boolean {
  // Solo los endpoints de INTERCAMBIO de credenciales van sin Bearer y no deben
  // disparar el ciclo refresh+retry: login, logout y los token/* (token,
  // token/refresh, token/verify). El resto bajo /auth/ (profile, profile/update,
  // change-password) SÍ requieren Authorization: Bearer — tratarlos como endpoints
  // de auth les quitaba el header y producía 401 (rompía hydrateSession → logout).
  return /\/auth\/(login|logout|token)\b/.test(endpoint);
}

function resolveUrl(endpoint: string): string {
  const isAbsolute = endpoint.startsWith('http://') || endpoint.startsWith('https://');
  return isAbsolute ? endpoint : `${API_URL}${endpoint}`;
}

function authHeaders(endpoint: string, extra?: HeadersInit): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  if (!isAuthEndpoint(endpoint) && accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  // Merge caller-provided headers last so they win.
  if (extra) {
    const normalized = new Headers(extra);
    normalized.forEach((value, key) => {
      headers[key] = value;
    });
  }
  return headers;
}

// ── AbortController + timeout (FE-HIGH-18) ────────────────────────────────────
function combineSignals(timeoutSignal: AbortSignal, callerSignal?: AbortSignal | null): AbortSignal {
  if (!callerSignal) return timeoutSignal;
  const anyFn = (AbortSignal as unknown as { any?: (signals: AbortSignal[]) => AbortSignal }).any;
  if (typeof anyFn === 'function') {
    return anyFn([timeoutSignal, callerSignal]);
  }
  // Best-effort combine: a controller that aborts when either source aborts.
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (callerSignal.aborted || timeoutSignal.aborted) {
    controller.abort();
  } else {
    callerSignal.addEventListener('abort', abort, { once: true });
    timeoutSignal.addEventListener('abort', abort, { once: true });
  }
  return controller.signal;
}

export interface RequestOptions extends RequestInit {
  /** Abort the request after this many ms. Default 30000; pass larger for downloads. */
  timeoutMs?: number;
}

/**
 * Performs a single fetch with the in-memory auth header, credentials (so the
 * httpOnly refresh cookie is sent), an abort timeout, and an optionally combined
 * caller signal. Does NOT handle 401 refresh — that lives in `request`.
 */
async function rawFetch(endpoint: string, options: RequestOptions = {}): Promise<Response> {
  const { timeoutMs = 30000, signal: callerSignal, headers: extraHeaders, ...rest } = options;
  const url = resolveUrl(endpoint);
  const timeoutController = new AbortController();
  const timer = setTimeout(() => timeoutController.abort(), timeoutMs);
  try {
    return await fetch(url, {
      ...rest,
      credentials: 'include',
      headers: authHeaders(endpoint, extraHeaders),
      signal: combineSignals(timeoutController.signal, callerSignal),
    });
  } finally {
    clearTimeout(timer);
  }
}

// ── 401 refresh + retry (FE-HIGH-11) ──────────────────────────────────────────
// A single shared in-flight refresh promise guards against concurrent refreshes:
// N parallel 401s await the same promise, so only ONE refresh request is issued.
let refreshPromise: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  try {
    const res = await rawFetch('/auth/token/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      timeoutMs: 15000,
    });
    if (!res.ok) {
      return false;
    }
    const data = (await res.json()) as { access?: string };
    if (!data.access) {
      return false;
    }
    setAccessToken(data.access);
    return true;
  } catch {
    return false;
  }
}

function refreshAccessToken(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

/**
 * Central request pipeline: auth header + timeout + 401 refresh/retry once.
 * Returns the raw Response (callers decide how to read the body).
 */
async function request(endpoint: string, options: RequestOptions = {}): Promise<Response> {
  let res = await rawFetch(endpoint, options);

  if (res.status === 401 && !isAuthEndpoint(endpoint)) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      // Retry the original request exactly once with the new token.
      res = await rawFetch(endpoint, options);
      if (res.status === 401) {
        signalLogout();
      }
    } else {
      signalLogout();
    }
  }
  return res;
}

async function buildError(res: Response, url: string): Promise<Error> {
  const errorText = await res.text();
  let errorObj: Record<string, string>;
  try {
    errorObj = JSON.parse(errorText);
  } catch {
    if (errorText.includes('<html') || errorText.includes('<!DOCTYPE html')) {
      errorObj = {
        error: `Error del servidor (${res.status}): Recibida respuesta HTML en lugar de JSON. Verifique que el endpoint existe y está configurado correctamente.`,
        details: `Endpoint: ${url}, Status: ${res.status}`,
      };
    } else {
      errorObj = { error: errorText };
    }
  }
  return new Error(JSON.stringify(errorObj));
}

// ── JSON fetcher (public API preserved) ───────────────────────────────────────
export async function fetcher<T>(endpoint: string, options?: RequestOptions): Promise<T> {
  const headers = {
    'Content-Type': 'application/json',
    ...(options?.headers || {}),
  };
  const res = await request(endpoint, { ...options, headers });
  if (!res.ok) {
    if (res.status === 401 && !isAuthEndpoint(endpoint)) {
      // signalLogout already fired inside request(); surface a friendly message.
      throw new Error('Sesión expirada. Redirigiendo al login...');
    }
    throw await buildError(res, resolveUrl(endpoint));
  }
  return res.json() as Promise<T>;
}

// ── Text / Blob / SSE helpers (FE-HIGH-14) ────────────────────────────────────
export async function fetchText(endpoint: string, options?: RequestOptions): Promise<string> {
  const res = await request(endpoint, options);
  if (!res.ok) {
    if (res.status === 401 && !isAuthEndpoint(endpoint)) {
      throw new Error('Sesión expirada. Redirigiendo al login...');
    }
    throw await buildError(res, resolveUrl(endpoint));
  }
  return res.text();
}

export async function fetchBlob(endpoint: string, options?: RequestOptions): Promise<Blob> {
  const res = await request(endpoint, { timeoutMs: 90000, ...options });
  if (!res.ok) {
    if (res.status === 401 && !isAuthEndpoint(endpoint)) {
      throw new Error('Sesión expirada. Redirigiendo al login...');
    }
    throw await buildError(res, resolveUrl(endpoint));
  }
  return res.blob();
}

export interface SSEEvent {
  text?: string;
  error?: string;
  [key: string]: unknown;
}

/**
 * Streams an SSE-style response (POST, `data: {...}` lines). Reuses the same
 * auth header + 401 refresh/retry + timeout pipeline. `onEvent` receives each
 * parsed JSON payload. The `[DONE]` sentinel ends the stream.
 */
export async function streamSSE(
  endpoint: string,
  onEvent: (event: SSEEvent) => void,
  options?: RequestOptions,
): Promise<void> {
  // SSE streams can run long; default to 90s unless the caller overrides.
  const res = await request(endpoint, { timeoutMs: 90000, ...options });
  if (!res.ok || !res.body) {
    if (res.status === 401 && !isAuthEndpoint(endpoint)) {
      throw new Error('Sesión expirada. Redirigiendo al login...');
    }
    throw new Error(`Error ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data:')) continue;
      const data = trimmed.slice(5).trim();
      if (data === '[DONE]') return;
      try {
        onEvent(JSON.parse(data) as SSEEvent);
      } catch {
        /* fragmento SSE parcial; se completa en la próxima iteración */
      }
    }
  }
}

// ── Convenience verbs (public API preserved) ──────────────────────────────────
export async function get<T>(endpoint: string): Promise<T> {
  return fetcher<T>(endpoint);
}

export async function post<T>(
  endpoint: string,
  data: Record<string, unknown>,
  options?: RequestOptions,
): Promise<T> {
  return fetcher<T>(endpoint, {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
    body: JSON.stringify(data),
  });
}

export async function patch<T>(endpoint: string, data: Record<string, unknown>): Promise<T> {
  return fetcher<T>(endpoint, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export async function put<T>(endpoint: string, data: Record<string, unknown>): Promise<T> {
  return fetcher<T>(endpoint, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export async function del<T>(endpoint: string): Promise<T> {
  return fetcher<T>(endpoint, { method: 'DELETE' });
}

/**
 * POST multipart/form-data (p. ej. import de CSV). NO fija Content-Type:
 * el navegador agrega el boundary correcto al serializar el FormData.
 */
export async function postForm<T>(endpoint: string, form: FormData): Promise<T> {
  const res = await request(endpoint, { method: 'POST', body: form });
  if (!res.ok) {
    throw await buildError(res, resolveUrl(endpoint));
  }
  return res.json() as Promise<T>;
}
