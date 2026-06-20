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
import {
  exportarConector,
  type ConectorInstancia,
  type ConectorProveedor,
} from '../services/integrationHubService';
import NuevoConectorModal from '../pages/Integraciones/NuevoConectorModal';
import { parseServiceAccount } from '../pages/Integraciones/serviceAccount';
import ConectorCard from '../pages/Integraciones/ConectorCard';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const PROV_SHEETS: ConectorProveedor = {
  id_proveedor: 'prov-sheets',
  codigo: 'google_sheets',
  nombre: 'Google Sheets',
  descripcion: '',
  icono_url: '',
  capacidades: ['contactos', 'productos', 'pedidos_venta'],
  estado: 'activo',
  versiones_soportadas: ['v4'],
};

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
  ultimo_sync: null,
  creado_en: '',
};

const INSTANCIA_SHEETS: ConectorInstancia = {
  ...INSTANCIA_ODOO,
  id_conector: 'inst-sheets-1',
  id_proveedor: 'prov-sheets',
  proveedor_nombre: 'Google Sheets',
  proveedor_codigo: 'google_sheets',
  nombre: 'Export Sheets',
  configuracion_publica: {},
};

const VALID_SA = JSON.stringify({
  type: 'service_account',
  project_id: 'demo',
  client_email: 'svc@demo.iam.gserviceaccount.com',
  private_key: '-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n',
});

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── parseServiceAccount ─────────────────────────────────────────────────────────

describe('parseServiceAccount', () => {
  it('rechaza string vacío', () => {
    expect(parseServiceAccount('   ')).toMatchObject({ ok: false });
  });

  it('rechaza JSON inválido', () => {
    expect(parseServiceAccount('{ no es json')).toMatchObject({ ok: false });
  });

  it('rechaza un JSON que no es cuenta de servicio', () => {
    expect(parseServiceAccount('{"foo": "bar"}')).toMatchObject({ ok: false });
  });

  it('acepta un service account válido y devuelve el objeto', () => {
    const res = parseServiceAccount(VALID_SA);
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.value.client_email).toBe('svc@demo.iam.gserviceaccount.com');
    }
  });
});

// ── exportarConector (service) ──────────────────────────────────────────────────

describe('exportarConector (service)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('POST al endpoint correcto con body vacío cuando no hay opciones', async () => {
    vi.mocked(post).mockResolvedValue({ mensaje: 'ok', task_id: 't1' });
    await exportarConector('abc');
    expect(post).toHaveBeenCalledWith('/integration-hub/instancias/abc/exportar/', {});
  });

  it('incluye tipos y full cuando se pasan', async () => {
    vi.mocked(post).mockResolvedValue({ mensaje: 'ok', task_id: 't1' });
    await exportarConector('abc', { tipos: ['contactos', 'productos'], full: true });
    expect(post).toHaveBeenCalledWith('/integration-hub/instancias/abc/exportar/', {
      tipos: ['contactos', 'productos'],
      full: true,
    });
  });

  it('omite tipos cuando es null pero envía full', async () => {
    vi.mocked(post).mockResolvedValue({ mensaje: 'ok', task_id: 't1' });
    await exportarConector('abc', { tipos: null, full: false });
    expect(post).toHaveBeenCalledWith('/integration-hub/instancias/abc/exportar/', { full: false });
  });
});

// ── NuevoConectorModal — flujo Google Sheets ────────────────────────────────────

describe('NuevoConectorModal — config Google Sheets', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // getProveedores y getConectores ambos usan get(); distinguimos por URL.
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.includes('proveedores')) {
        return Promise.resolve({ results: [PROV_ODOO, PROV_SHEETS], count: 2, next: null, previous: null });
      }
      return Promise.resolve({ results: [INSTANCIA_ODOO], count: 1, next: null, previous: null });
    });
    vi.mocked(post).mockResolvedValue(INSTANCIA_SHEETS);
  });

  async function abrirPaso2Sheets() {
    const user = userEvent.setup();
    renderWithProviders(<NuevoConectorModal onClose={() => {}} />);
    // Paso 1: elegir el proveedor Google Sheets.
    await user.click(await screen.findByText('Google Sheets'));
    // Ya en paso 2 aparecen campos específicos.
    await screen.findByLabelText(/Service Account JSON/i);
    return user;
  }

  it('muestra campos específicos de Sheets y el selector de origen poblado (sin Sheets)', async () => {
    await abrirPaso2Sheets();
    expect(screen.getByLabelText(/Conector de origen/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Service Account JSON/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/carpeta de Drive/i)).toBeInTheDocument();
  });

  it('crea el conector con configuracion de Sheets bien formada', async () => {
    const user = await abrirPaso2Sheets();
    await user.type(screen.getByLabelText(/Nombre del conector/i), 'Mi Export');

    // Seleccionar conector de origen.
    await user.click(screen.getByLabelText(/Conector de origen/i));
    await user.click(await screen.findByText(/Odoo Producción — Odoo/i));

    // Pegar service account (fireEvent: el JSON tiene llaves que userEvent.type interpreta).
    fireEvent.change(screen.getByLabelText(/Service Account JSON/i), { target: { value: VALID_SA } });

    // Marcar una entidad.
    await user.click(screen.getByLabelText('contactos'));

    await user.click(screen.getByRole('button', { name: /crear conector/i }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [url, body] = vi.mocked(post).mock.calls[0];
    expect(url).toBe('/integration-hub/instancias/');
    const b = body as Record<string, unknown>;
    expect(b.id_proveedor).toBe('prov-sheets');
    expect(b.nombre).toBe('Mi Export');
    expect(b.entidades_activas).toEqual(['contactos']);
    const conf = b.configuracion as Record<string, unknown>;
    expect(conf.source_instancia_id).toBe('inst-odoo-1');
    expect((conf.service_account as Record<string, unknown>).client_email).toBe(
      'svc@demo.iam.gserviceaccount.com',
    );
  });

  it('muestra error y no envía si el service account no es JSON válido', async () => {
    const user = await abrirPaso2Sheets();
    await user.type(screen.getByLabelText(/Nombre del conector/i), 'Mi Export');
    await user.click(screen.getByLabelText(/Conector de origen/i));
    await user.click(await screen.findByText(/Odoo Producción — Odoo/i));
    fireEvent.change(screen.getByLabelText(/Service Account JSON/i), { target: { value: '{ roto' } });

    await user.click(screen.getByRole('button', { name: /crear conector/i }));

    expect(await screen.findByText(/El JSON no es válido/i)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('deshabilita Crear hasta tener nombre, origen y service account', async () => {
    const user = await abrirPaso2Sheets();
    const btn = screen.getByRole('button', { name: /crear conector/i });
    expect(btn).toBeDisabled();
    await user.type(screen.getByLabelText(/Nombre del conector/i), 'X');
    expect(btn).toBeDisabled(); // falta origen + SA
  });
});

// ── ConectorCard — botón Exportar ahora ─────────────────────────────────────────

describe('ConectorCard — exportar', () => {
  beforeEach(() => vi.clearAllMocks());

  it('muestra "Exportar ahora" solo para conectores google_sheets', () => {
    const { rerender } = renderWithProviders(<ConectorCard conector={INSTANCIA_ODOO} />);
    expect(screen.queryByRole('button', { name: /exportar ahora/i })).not.toBeInTheDocument();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConectorCard conector={INSTANCIA_SHEETS} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole('button', { name: /exportar ahora/i })).toBeInTheDocument();
  });

  it('al pulsar Exportar llama al service y muestra feedback', async () => {
    vi.mocked(post).mockResolvedValue({ mensaje: 'Exportación encolada', task_id: 't9' });
    const user = userEvent.setup();
    renderWithProviders(<ConectorCard conector={INSTANCIA_SHEETS} />);

    await user.click(screen.getByRole('button', { name: /exportar ahora/i }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/integration-hub/instancias/inst-sheets-1/exportar/', {}),
    );
    expect(await screen.findByText(/Exportación encolada/i)).toBeInTheDocument();
  });
});
