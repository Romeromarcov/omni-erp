/**
 * Cobertura exhaustiva de las páginas de Integraciones poco testeadas:
 *  - IntegrationHubPage: apertura del modal (header y estado vacío), render de
 *    la grilla de conectores poblada y estado de carga.
 *  - NuevoConectorModal: flujo Odoo/API (paso 1 → paso 2, validación de
 *    requeridos, whitelist del payload, toggle de entidades, intervalo de sync,
 *    error de backend, proveedor "próximamente" deshabilitado, botón Atrás).
 *
 * Complementa (no duplica) IntegrationHubPage.test.tsx (contrato /status/) e
 * IntegracionesSheets.test.tsx (flujo Google Sheets).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

import { get, post } from '../services/api';
import IntegrationHubPage from '../pages/Integraciones/IntegrationHubPage';
import NuevoConectorModal from '../pages/Integraciones/NuevoConectorModal';
import type { ConectorInstancia, ConectorProveedor } from '../services/integrationHubService';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const PROV_ODOO: ConectorProveedor = {
  id_proveedor: 'prov-odoo',
  codigo: 'odoo',
  nombre: 'Odoo',
  descripcion: '',
  icono_url: '',
  capacidades: ['contactos', 'productos'],
  estado: 'activo',
  versiones_soportadas: ['16'],
  requiere_db: true,
};

const PROV_API_SAAS: ConectorProveedor = {
  id_proveedor: 'prov-saas',
  codigo: 'odoo_saas',
  nombre: 'Odoo SaaS',
  descripcion: '',
  icono_url: '',
  capacidades: ['contactos'],
  estado: 'activo',
  versiones_soportadas: ['17'],
  requiere_db: false,
};

const PROV_PROXIMAMENTE: ConectorProveedor = {
  id_proveedor: 'prov-soon',
  codigo: 'shopify',
  nombre: 'Shopify',
  descripcion: '',
  icono_url: '',
  capacidades: ['pedidos'],
  estado: 'proximamente',
  versiones_soportadas: [],
};

const INSTANCIA_ODOO: ConectorInstancia = {
  id_conector: 'inst-odoo-1',
  id_empresa: 'e1',
  id_proveedor: 'prov-odoo',
  proveedor_nombre: 'Odoo',
  proveedor_codigo: 'odoo',
  proveedor_capacidades: ['contactos', 'productos'],
  nombre: 'Odoo Producción',
  estado: 'activo',
  intervalo_sync_minutos: 60,
  entidades_activas: ['contactos'],
  version_detectada: '16',
  configuracion_publica: { host: 'https://x.odoo.com' },
  ultimo_sync: '2026-06-20T10:00:00Z',
  creado_en: '2026-06-01T00:00:00Z',
};

const STATUS_FULL = {
  conectores: { total: 1, activos: 1, con_error: 0, configurando: 0, inactivos: 0 },
  jobs_24h: { total: 5, completados: 5, con_errores: 0, fallidos: 0, en_progreso: 0 },
  proveedores_disponibles: ['odoo'],
};

function makeGetImpl(opts: {
  proveedores?: ConectorProveedor[];
  instancias?: ConectorInstancia[];
  status?: unknown;
}) {
  const provs = opts.proveedores ?? [PROV_ODOO];
  const insts = opts.instancias ?? [];
  return (url: string) => {
    if (url.includes('proveedores')) {
      return Promise.resolve({ results: provs, count: provs.length, next: null, previous: null });
    }
    if (url.includes('status')) {
      return Promise.resolve(opts.status ?? STATUS_FULL);
    }
    // instancias
    return Promise.resolve({ results: insts, count: insts.length, next: null, previous: null });
  };
}

/** Rellena un TextField por su label de forma síncrona (rápido, sin flakiness). */
function fill(labelRe: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(labelRe), { target: { value } });
}

/** Completa los 5 campos requeridos del formulario Odoo/API. */
function fillCamposApi(opts: { nombre: string; host: string; db?: string; user: string; apiKey: string }) {
  fill(/Nombre del conector/i, opts.nombre);
  fill(/URL del servidor/i, opts.host);
  if (opts.db !== undefined) fill(/^Base de datos \*/i, opts.db);
  fill(/Usuario \/ Email/i, opts.user);
  fill(/API Key/i, opts.apiKey);
}

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── IntegrationHubPage ──────────────────────────────────────────────────────────

describe('IntegrationHubPage — grilla y apertura del modal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renderiza la grilla de conectores cuando hay instancias', async () => {
    vi.mocked(get).mockImplementation(makeGetImpl({ instancias: [INSTANCIA_ODOO] }));
    renderWithProviders(<IntegrationHubPage />);

    expect(await screen.findByText('Odoo Producción')).toBeInTheDocument();
    // No debe mostrarse el estado vacío.
    expect(screen.queryByText('Sin conectores configurados')).not.toBeInTheDocument();
    // KPIs del status presentes.
    expect(screen.getByText('Conectores activos')).toBeInTheDocument();
  });

  it('abre el modal "Nuevo conector" desde el header', async () => {
    vi.mocked(get).mockImplementation(makeGetImpl({ instancias: [INSTANCIA_ODOO] }));
    const user = userEvent.setup();
    renderWithProviders(<IntegrationHubPage />);

    await screen.findByText('Odoo Producción');
    await user.click(screen.getByRole('button', { name: /nuevo conector/i }));

    // El modal abre en paso 1 (selección de proveedor).
    expect(await screen.findByText('Seleccionar proveedor')).toBeInTheDocument();
  });

  it('abre el modal desde el botón del estado vacío y permite cerrarlo', async () => {
    vi.mocked(get).mockImplementation(makeGetImpl({ instancias: [] }));
    const user = userEvent.setup();
    renderWithProviders(<IntegrationHubPage />);

    await user.click(await screen.findByRole('button', { name: /agregar primer conector/i }));
    expect(await screen.findByText('Seleccionar proveedor')).toBeInTheDocument();

    // Cerrar con el icono de la X (IconButton del DialogTitle).
    await user.click(screen.getByTestId('CloseIcon').closest('button')!);
    await waitFor(() =>
      expect(screen.queryByText('Seleccionar proveedor')).not.toBeInTheDocument(),
    );
  });

  it('muestra el spinner de carga mientras se resuelven los conectores', async () => {
    let resolveInst!: (v: unknown) => void;
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.includes('proveedores')) {
        return Promise.resolve({ results: [], count: 0, next: null, previous: null });
      }
      if (url.includes('status')) return Promise.resolve(STATUS_FULL);
      return new Promise((res) => { resolveInst = res; });
    });
    renderWithProviders(<IntegrationHubPage />);

    // Mientras la promesa de instancias no resuelve, se ve el CircularProgress.
    expect(await screen.findByRole('progressbar')).toBeInTheDocument();

    resolveInst({ results: [], count: 0, next: null, previous: null });
    expect(await screen.findByText('Sin conectores configurados')).toBeInTheDocument();
  });
});

// ── NuevoConectorModal — flujo Odoo / API ───────────────────────────────────────

describe('NuevoConectorModal — flujo Odoo/API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockImplementation(
      makeGetImpl({ proveedores: [PROV_ODOO, PROV_API_SAAS, PROV_PROXIMAMENTE], instancias: [] }),
    );
    vi.mocked(post).mockResolvedValue(INSTANCIA_ODOO);
  });

  async function abrirPaso2Odoo(prov = 'Odoo') {
    const user = userEvent.setup();
    renderWithProviders(<NuevoConectorModal onClose={() => {}} />);
    await user.click(await screen.findByText(prov));
    await screen.findByLabelText(/URL del servidor/i);
    return user;
  }

  it('paso 1 deshabilita los proveedores "próximamente"', async () => {
    renderWithProviders(<NuevoConectorModal onClose={() => {}} />);
    await screen.findByText('Odoo');
    expect(screen.getByText('Próximamente')).toBeInTheDocument();
    // La CardActionArea de Shopify queda disabled (su botón).
    const shopifyCard = screen.getByText('Shopify').closest('button')!;
    expect(shopifyCard).toBeDisabled();
  });

  it('muestra campos de API y oculta los de Sheets en paso 2', async () => {
    await abrirPaso2Odoo();
    expect(screen.getByLabelText(/URL del servidor/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Usuario \/ Email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/API Key/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Service Account JSON/i)).not.toBeInTheDocument();
  });

  it('marca "Base de datos" como requerida cuando requiere_db es true', async () => {
    await abrirPaso2Odoo('Odoo');
    // Odoo requiere_db=true → label "Base de datos" (sin "(opcional)").
    expect(screen.getByLabelText(/^Base de datos \*/i)).toBeInTheDocument();
  });

  it('marca "Base de datos (opcional)" cuando requiere_db es false', async () => {
    await abrirPaso2Odoo('Odoo SaaS');
    expect(screen.getByLabelText(/Base de datos \(opcional\)/i)).toBeInTheDocument();
  });

  it('mantiene "Crear" deshabilitado hasta completar los requeridos de API', async () => {
    await abrirPaso2Odoo();
    const btn = screen.getByRole('button', { name: /crear conector/i });
    expect(btn).toBeDisabled();

    fill(/Nombre del conector/i, 'Mi Odoo');
    expect(btn).toBeDisabled(); // falta host, user, api_key
    fill(/URL del servidor/i, 'https://x.odoo.com');
    expect(btn).toBeDisabled();
    fill(/Usuario \/ Email/i, 'admin@x.com');
    expect(btn).toBeDisabled();
    fill(/API Key/i, 'secret');
    expect(btn).toBeEnabled();
  });

  it('envía el payload de API con la whitelist correcta (host/db/user/api_key/timeout)', async () => {
    const user = await abrirPaso2Odoo();
    fillCamposApi({ nombre: 'Mi Odoo', host: 'https://x.odoo.com', db: 'midb', user: 'admin@x.com', apiKey: 'secret' });

    // Toggle de una entidad.
    await user.click(screen.getByLabelText('productos'));

    await user.click(screen.getByRole('button', { name: /crear conector/i }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [url, body] = vi.mocked(post).mock.calls[0];
    expect(url).toBe('/integration-hub/instancias/');
    const b = body as Record<string, unknown>;
    expect(b.id_proveedor).toBe('prov-odoo');
    expect(b.nombre).toBe('Mi Odoo');
    expect(b.entidades_activas).toEqual(['productos']);
    expect(b.intervalo_sync_minutos).toBe(60);
    const conf = b.configuracion as Record<string, unknown>;
    expect(conf).toEqual({
      host: 'https://x.odoo.com',
      db: 'midb',
      user: 'admin@x.com',
      api_key: 'secret',
      timeout: 30,
    });
    // No debe filtrar campos de Sheets.
    expect(conf.service_account).toBeUndefined();
    expect(conf.source_instancia_id).toBeUndefined();
  });

  it('omite db (undefined) cuando se deja vacío', async () => {
    const user = await abrirPaso2Odoo('Odoo SaaS');
    fillCamposApi({ nombre: 'SaaS', host: 'https://y.odoo.com', user: 'admin@y.com', apiKey: 'k' });

    await user.click(screen.getByRole('button', { name: /crear conector/i }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const conf = (vi.mocked(post).mock.calls[0][1] as Record<string, unknown>)
      .configuracion as Record<string, unknown>;
    expect(conf.db).toBeUndefined();
  });

  it('permite cambiar el intervalo de sync y lo refleja en el payload', async () => {
    const user = await abrirPaso2Odoo();
    fillCamposApi({ nombre: 'Mi Odoo', host: 'https://x.odoo.com', db: 'midb', user: 'admin@x.com', apiKey: 'secret' });

    await user.click(screen.getByLabelText(/Intervalo de sync/i));
    await user.click(await screen.findByText('Diario'));

    await user.click(screen.getByRole('button', { name: /crear conector/i }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect((vi.mocked(post).mock.calls[0][1] as Record<string, unknown>).intervalo_sync_minutos).toBe(1440);
  });

  it('vuelve a paso 1 con el botón "Atrás"', async () => {
    const user = await abrirPaso2Odoo();
    await user.click(screen.getByRole('button', { name: /atrás/i }));
    expect(await screen.findByText('Seleccionar proveedor')).toBeInTheDocument();
  });

  it('muestra el error del backend (JSON formateado) cuando crearConector falla', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('{"host":["URL inválida"]}'));
    const user = await abrirPaso2Odoo();
    fillCamposApi({ nombre: 'Mi Odoo', host: 'bad', db: 'midb', user: 'admin@x.com', apiKey: 'secret' });

    await user.click(screen.getByRole('button', { name: /crear conector/i }));

    expect(await screen.findByText(/URL inválida/i)).toBeInTheDocument();
  });

  it('muestra el error crudo cuando el mensaje de error no es JSON', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('Network Error'));
    const user = await abrirPaso2Odoo();
    fillCamposApi({ nombre: 'Mi Odoo', host: 'https://x.odoo.com', db: 'midb', user: 'admin@x.com', apiKey: 'secret' });

    await user.click(screen.getByRole('button', { name: /crear conector/i }));

    expect(await screen.findByText('Network Error')).toBeInTheDocument();
  });

  it('cierra el modal al crear exitosamente (onClose se invoca)', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<NuevoConectorModal onClose={onClose} />);
    await user.click(await screen.findByText('Odoo'));
    await screen.findByLabelText(/URL del servidor/i);

    fillCamposApi({ nombre: 'Mi Odoo', host: 'https://x.odoo.com', db: 'midb', user: 'admin@x.com', apiKey: 'secret' });

    await user.click(screen.getByRole('button', { name: /crear conector/i }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('destildar una entidad la quita de entidades_activas', async () => {
    const user = await abrirPaso2Odoo();
    const checkboxContactos = screen.getByLabelText('contactos');
    await user.click(checkboxContactos); // marca
    await user.click(checkboxContactos); // desmarca

    fillCamposApi({ nombre: 'Mi Odoo', host: 'https://x.odoo.com', db: 'midb', user: 'admin@x.com', apiKey: 'secret' });
    await user.click(screen.getByRole('button', { name: /crear conector/i }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect((vi.mocked(post).mock.calls[0][1] as Record<string, unknown>).entidades_activas).toEqual([]);
  });

  it('el selector de origen Sheets avisa cuando no hay conectores de origen', async () => {
    // Solo Sheets disponible, sin instancias de origen.
    const PROV_SHEETS: ConectorProveedor = {
      ...PROV_ODOO, id_proveedor: 'prov-sheets', codigo: 'google_sheets', nombre: 'Google Sheets',
      capacidades: ['contactos'], requiere_db: undefined,
    };
    vi.mocked(get).mockImplementation(makeGetImpl({ proveedores: [PROV_SHEETS], instancias: [] }));
    const user = userEvent.setup();
    renderWithProviders(<NuevoConectorModal onClose={() => {}} />);
    await user.click(await screen.findByText('Google Sheets'));
    expect(
      await screen.findByText(/Crea primero un conector de origen/i),
    ).toBeInTheDocument();
  });
});
