import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));

import { get, post, patch, del } from '../services/api';
import IntegracionB2bPage from '../pages/IntegracionB2b/IntegracionB2bPage';

const configApi = {
  id_configuracion: 'cfg1',
  id_empresa: 'e1',
  nombre_integracion: 'SAP B2B',
  tipo_integracion: 'REST',
  url_endpoint: 'https://api.ejemplo.com',
  credenciales_json: { token: 'abc' },
  formato_datos: 'JSON',
  activo: true,
};

const mapeoApi = {
  id_mapeo_campo: 'm1',
  id_configuracion_integracion: 'cfg1',
  nombre_campo_interno: 'razon_social',
  nombre_campo_externo: 'CompanyName',
  activo: true,
};

const logApi = {
  id_log_integracion: 'l1',
  id_configuracion: 'cfg1',
  fecha_hora: '2026-06-24T10:30:00Z',
  tipo_transaccion: 'PUSH',
  estado_integracion: 'error',
  mensaje_error: 'Timeout del endpoint',
  duracion_ms: 1500,
};

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/integracion-b2b/configuracion-integracion'))
      return Promise.resolve([configApi]);
    if (url.startsWith('/integracion-b2b/mapeo-campos')) return Promise.resolve([mapeoApi]);
    if (url.startsWith('/integracion-b2b/logs-integracion')) return Promise.resolve([logApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <IntegracionB2bPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const irAMapeo = () => fireEvent.click(screen.getByRole('tab', { name: 'Mapeo de campos' }));
const irALogs = () => fireEvent.click(screen.getByRole('tab', { name: 'Logs' }));

describe('IntegracionB2bPage — tab Configuraciones', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('renderiza el encabezado y los tres tabs', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { name: 'Integración B2B' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Configuraciones' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Mapeo de campos' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Logs' })).toBeInTheDocument();
  });

  it('lista las configuraciones', async () => {
    renderPage();
    expect(await screen.findByText('SAP B2B')).toBeInTheDocument();
    expect(screen.getByText('REST')).toBeInTheDocument();
  });

  it('muestra el estado vacío cuando no hay configuraciones', async () => {
    vi.mocked(get).mockResolvedValue([]);
    renderPage();
    expect(
      await screen.findByText(/Sin configuraciones de integración/),
    ).toBeInTheDocument();
  });

  it('valida el nombre requerido al crear', async () => {
    renderPage();
    await screen.findByText('SAP B2B');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva configuración' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Indique el nombre de la integración/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('valida que las credenciales JSON sean válidas', async () => {
    renderPage();
    await screen.findByText('SAP B2B');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva configuración' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Nombre de la integración/), {
      target: { value: 'Nueva' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Tipo de integración/), {
      target: { value: 'SOAP' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Credenciales JSON/), {
      target: { value: '{ no es json' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Las credenciales JSON no son válidas/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una configuración con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValue({ id_configuracion: 'cfg2' });
    renderPage();
    await screen.findByText('SAP B2B');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva configuración' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Nombre de la integración/), {
      target: { value: 'Odoo Sync' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Tipo de integración/), {
      target: { value: 'REST' },
    });
    fireEvent.change(within(dialog).getByLabelText(/URL del endpoint/), {
      target: { value: 'https://odoo.local/api' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Credenciales JSON/), {
      target: { value: '{"key":"v"}' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/integracion-b2b/configuracion-integracion/',
        expect.objectContaining({
          id_empresa: 'e1',
          nombre_integracion: 'Odoo Sync',
          tipo_integracion: 'REST',
          url_endpoint: 'https://odoo.local/api',
          credenciales_json: { key: 'v' },
          formato_datos: 'JSON',
          activo: true,
        }),
      ),
    );
  });

  it('muestra el error del backend sin cerrar el diálogo', async () => {
    vi.mocked(post).mockRejectedValue(new Error('boom'));
    renderPage();
    await screen.findByText('SAP B2B');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva configuración' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Nombre de la integración/), {
      target: { value: 'Falla' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Tipo de integración/), {
      target: { value: 'REST' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/boom/)).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('edita una configuración por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_configuracion: 'cfg1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Nombre de la integración/), {
      target: { value: 'SAP B2B v2' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/integracion-b2b/configuracion-integracion/cfg1/',
        expect.objectContaining({ nombre_integracion: 'SAP B2B v2' }),
      ),
    );
  });

  it('elimina con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/integracion-b2b/configuracion-integracion/cfg1/'),
    );
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});

describe('IntegracionB2bPage — tab Mapeo de campos', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('muestra el estado vacío hasta seleccionar una configuración', async () => {
    renderPage();
    irAMapeo();
    expect(
      await screen.findByText(/Seleccione una configuración para ver y editar/),
    ).toBeInTheDocument();
  });

  it('lista los mapeos al seleccionar una configuración', async () => {
    renderPage();
    await screen.findByText('SAP B2B');
    irAMapeo();
    const combos = await screen.findAllByLabelText(/Configuración/);
    fireEvent.mouseDown(combos[0]);
    fireEvent.click(await screen.findByRole('option', { name: 'SAP B2B' }));
    expect(await screen.findByText('razon_social')).toBeInTheDocument();
    expect(screen.getByText('CompanyName')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(
      '/integracion-b2b/mapeo-campos/?id_configuracion_integracion=cfg1',
    );
  });

  it('crea un mapeo con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValue({ id_mapeo_campo: 'm2' });
    renderPage();
    await screen.findByText('SAP B2B');
    irAMapeo();
    const combos = await screen.findAllByLabelText(/Configuración/);
    fireEvent.mouseDown(combos[0]);
    fireEvent.click(await screen.findByRole('option', { name: 'SAP B2B' }));
    await screen.findByText('razon_social');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo mapeo' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Campo interno/), {
      target: { value: 'rif' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Campo externo/), {
      target: { value: 'TaxId' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/integracion-b2b/mapeo-campos/',
        expect.objectContaining({
          id_configuracion_integracion: 'cfg1',
          nombre_campo_interno: 'rif',
          nombre_campo_externo: 'TaxId',
          activo: true,
        }),
      ),
    );
  });

  it('valida el campo interno requerido al crear', async () => {
    renderPage();
    await screen.findByText('SAP B2B');
    irAMapeo();
    const combos = await screen.findAllByLabelText(/Configuración/);
    fireEvent.mouseDown(combos[0]);
    fireEvent.click(await screen.findByRole('option', { name: 'SAP B2B' }));
    await screen.findByText('razon_social');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo mapeo' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique el campo interno/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('elimina un mapeo con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('SAP B2B');
    irAMapeo();
    const combos = await screen.findAllByLabelText(/Configuración/);
    fireEvent.mouseDown(combos[0]);
    fireEvent.click(await screen.findByRole('option', { name: 'SAP B2B' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/integracion-b2b/mapeo-campos/m1/'),
    );
    confirmSpy.mockRestore();
  });
});

describe('IntegracionB2bPage — tab Logs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('muestra el estado vacío hasta seleccionar una configuración', async () => {
    renderPage();
    irALogs();
    expect(
      await screen.findByText(/Seleccione una configuración para ver su bitácora/),
    ).toBeInTheDocument();
  });

  it('lista los logs (solo lectura) al filtrar por configuración', async () => {
    renderPage();
    await screen.findByText('SAP B2B');
    irALogs();
    const combos = await screen.findAllByLabelText(/Configuración/);
    fireEvent.mouseDown(combos[0]);
    fireEvent.click(await screen.findByRole('option', { name: 'SAP B2B' }));
    expect(await screen.findByText('Timeout del endpoint')).toBeInTheDocument();
    expect(screen.getByText('PUSH')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(
      '/integracion-b2b/logs-integracion/?id_configuracion=cfg1',
    );
    // Solo lectura: no hay acciones de crear/editar/eliminar en este tab.
    expect(screen.queryByRole('button', { name: 'Nuevo log' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Eliminar' })).not.toBeInTheDocument();
  });
});
