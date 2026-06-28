import { expect, type Page } from '@playwright/test';

/**
 * Sesión E2E (TEST-6 / Fase 4).
 *
 * Los specs de flujos críticos comparten un mismo patrón de arranque:
 *   1. Login programático vía `POST /api/auth/login/` usando el request context
 *      de la página (la cookie httpOnly `refresh_token` queda en el contexto del
 *      navegador, y el frontend rehidrata la sesión al cargar cualquier ruta).
 *   2. Resolución de la empresa "primaria" del usuario (la que el backend
 *      inyecta al crear documentos vía `EmpresaInjectMixin`): es la primera
 *      empresa visible ordenada por `nombre_legal` (Empresa.Meta.ordering).
 *   3. Selección de empresa/sucursal en localStorage (lo mismo que persiste la
 *      pantalla de login), para las páginas que leen `id_empresa`/`id_sucursal`.
 *
 * Credenciales: las crea `manage.py seed_empresa_inicial` (ver README de e2e y
 * el job "e2e" de CI). La contraseña NUNCA va en el código (R-CODE-8): se toma
 * de `E2E_ADMIN_PASSWORD`.
 */

const USUARIO = process.env.E2E_ADMIN_USER ?? 'admin_e2e';
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? '';

/** Archivo de storageState del login único (ver `global.setup.ts` y la config). */
export const AUTH_STORAGE_FILE = 'e2e/.auth/admin.json';

interface Paginado<T> {
  results: T[];
}

/** Normaliza respuestas de lista DRF (paginadas o no) a un arreglo. */
export function aLista<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object' && 'results' in data) {
    return (data as Paginado<T>).results;
  }
  return [];
}

/** Cliente API mínimo sobre el request context del navegador (proxy /api). */
export class ApiE2E {
  constructor(
    private readonly page: Page,
    readonly access: string,
  ) {}

  private cabeceras(): Record<string, string> {
    return { Authorization: `Bearer ${this.access}` };
  }

  async get<T>(ruta: string): Promise<T> {
    const resp = await this.page.request.get(`/api${ruta}`, { headers: this.cabeceras() });
    expect(resp.ok(), `GET ${ruta} → ${resp.status()}: ${await resp.text()}`).toBeTruthy();
    return (await resp.json()) as T;
  }

  async post<T>(ruta: string, data: Record<string, unknown>): Promise<T> {
    const resp = await this.page.request.post(`/api${ruta}`, {
      headers: this.cabeceras(),
      data,
    });
    expect(resp.ok(), `POST ${ruta} → ${resp.status()}: ${await resp.text()}`).toBeTruthy();
    return (await resp.json()) as T;
  }
}

export interface EmpresaApi {
  id_empresa: string;
  nombre_legal: string;
}

interface SucursalApi {
  id_sucursal: string;
  nombre: string;
  id_empresa: string | { id_empresa: string };
}

export interface SesionE2E {
  api: ApiE2E;
  /** Empresa "primaria": la que el backend inyecta al crear documentos. */
  empresaId: string;
  empresaNombre: string;
  sucursalId: string;
  /** Todas las empresas visibles del usuario (para el flujo multi-empresa). */
  empresas: EmpresaApi[];
}

export function credencialesE2E(): { usuario: string; password: string } {
  if (!PASSWORD) {
    throw new Error(
      'E2E_ADMIN_PASSWORD no está definida. Corre `manage.py seed_empresa_inicial` ' +
        'con OMNI_SEED_ADMIN_PASSWORD y exporta el mismo valor en E2E_ADMIN_PASSWORD ' +
        '(ver frontend/e2e/README.md).',
    );
  }
  return { usuario: USUARIO, password: PASSWORD };
}

/**
 * Login programático con un reintento ante el rate-limit del backend
 * (SEC-07: 5 logins/min por IP). El refresh token queda como cookie httpOnly
 * en el contexto del navegador.
 */
async function loginApi(page: Page): Promise<string> {
  const { usuario, password } = credencialesE2E();
  for (let intento = 0; intento < 2; intento += 1) {
    const resp = await page.request.post('/api/auth/login/', {
      data: { username: usuario, password },
    });
    if (resp.status() === 429 && intento === 0) {
      // Ventana del rate-limit: esperar a que expire y reintentar una vez.
      await page.waitForTimeout(61_000);
      continue;
    }
    expect(resp.ok(), `login API → ${resp.status()}: ${await resp.text()}`).toBeTruthy();
    const cuerpo = (await resp.json()) as { access: string };
    return cuerpo.access;
  }
  throw new Error('Login E2E: rate limit persistente (429).');
}

function idDeEmpresa(sucursal: SucursalApi): string {
  return typeof sucursal.id_empresa === 'object'
    ? sucursal.id_empresa.id_empresa
    : sucursal.id_empresa;
}

/**
 * Obtiene un `access` fresco SIN hacer login: usa la cookie `refresh_token` que
 * el `storageState` (login único en global.setup) ya trae. `/token/refresh/` no
 * está bajo el throttle de login (5/min, SEC-07), así que cada spec puede pedir
 * el suyo (token de 15 min) sin agotar la ventana. Si no hay cookie (p.ej. una
 * corrida sin el proyecto `setup`), cae a un login directo.
 */
async function accessFresco(page: Page): Promise<string> {
  const resp = await page.request.post('/api/auth/token/refresh/', { data: {} });
  if (resp.ok()) {
    const cuerpo = (await resp.json()) as { access?: string };
    if (cuerpo.access) return cuerpo.access;
  }
  return loginApi(page);
}

/** Inicia sesión (API) y deja el contexto listo para navegar la app autenticada. */
export async function iniciarSesion(page: Page): Promise<SesionE2E> {
  const access = await accessFresco(page);
  const api = new ApiE2E(page, access);

  const empresas = aLista<EmpresaApi>(await api.get('/core/empresas/')).slice();
  expect(empresas.length, 'el seed debe crear al menos una empresa').toBeGreaterThan(0);
  // Empresa primaria = primera por nombre_legal (Empresa.Meta.ordering): es la
  // que EmpresaInjectMixin asigna a pedidos/notas/facturas creados via API.
  empresas.sort((a, b) => a.nombre_legal.localeCompare(b.nombre_legal, 'es'));
  const primaria = empresas[0];

  const sucursales = aLista<SucursalApi>(await api.get('/core/sucursales/'));
  const sucursal = sucursales.find((s) => idDeEmpresa(s) === primaria.id_empresa);
  expect(sucursal, 'la empresa primaria debe tener al menos una sucursal').toBeTruthy();

  // Replica la selección de empresa/sucursal que hace la pantalla de login.
  await page.addInitScript(
    ([idEmpresa, idSucursal]) => {
      localStorage.setItem('id_empresa', idEmpresa);
      localStorage.setItem('id_sucursal', idSucursal);
    },
    [primaria.id_empresa, (sucursal as SucursalApi).id_sucursal] as const,
  );

  return {
    api,
    empresaId: primaria.id_empresa,
    empresaNombre: primaria.nombre_legal,
    sucursalId: (sucursal as SucursalApi).id_sucursal,
    empresas,
  };
}

/** Mismo formato de moneda que usa el Dashboard de Cartera (`money()`). */
export function formatoMonedaDashboard(valor: string | number): string {
  return `$${parseFloat(String(valor)).toLocaleString('es-VE', { minimumFractionDigits: 2 })}`;
}
