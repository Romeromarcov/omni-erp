export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export async function fetcher<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('token');
  const isAuthEndpoint = endpoint.startsWith('/auth/login') || endpoint.startsWith('/auth/token');
  const headers = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    ...(!isAuthEndpoint && token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options?.headers || {}),
  };
  const isAbsolute = endpoint.startsWith('http://') || endpoint.startsWith('https://');
  const url = isAbsolute ? endpoint : `${API_URL}${endpoint}`;
  const res = await fetch(url, { ...options, headers });

  if (!res.ok) {
    if (res.status === 401 && !isAuthEndpoint && !window.location.pathname.startsWith('/login')) {
      localStorage.removeItem('token');
      localStorage.removeItem('usuario');
      localStorage.removeItem('empresa');
      localStorage.removeItem('sucursal');
      localStorage.removeItem('id_empresa');
      localStorage.removeItem('id_sucursal');
      window.location.href = '/login';
      throw new Error('Sesión expirada. Redirigiendo al login...');
    }
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
    throw new Error(JSON.stringify(errorObj));
  }
  return res.json();
}

export async function get<T>(endpoint: string): Promise<T> {
  return fetcher<T>(endpoint);
}

export async function post<T>(endpoint: string, data: Record<string, unknown>): Promise<T> {
  return fetcher<T>(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
