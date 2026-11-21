import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

import { get, post, patch } from '../services/api';
import EditarConectorModal from '../pages/Integraciones/EditarConectorModal';
import ConectorDetallePage from '../pages/Integraciones/ConectorDetallePage';
import type { ConectorInstancia } from '../services/integrationHubService';

const BASE_CONECTOR: ConectorInstancia = {
  id_conector: 'inst-odoo-1',
  id_empresa: 'emp-1',
  id_proveedor: 'prov-odoo',
  proveedor_nombre: 'Odoo',
  proveedor_codigo: 'odoo',
  proveedor_capacidades: ['contactos', 'productos', 'pagos', 'gestiones_cobranza'],
  nombre: 'Odoo QA',
  estado: 'activo',
  intervalo_sync_minutos: 60,
  entidades_activas: ['pagos', 'gestiones_cobranza'],
  version_detectada: '18.0',
  configuracion_publica: {
    host: 'https://qa.odoo.com',
    db: 'qa_db',
    user: 'read@qa.com',
    timeout: 30,
    push_habilitado: false,
    push_modo_pago: 'borrador',
    write_user: '',
    tiene_write_api_key: false,
    diario_pagos_default_id: null,
  },
  ultimo_sync: null,
  creado_en: '2026-11-20T00:00:00Z',
};

function renderWithProviders(ui: React.ReactNode, initialRoute = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialRoute]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('EditarConectorModal — configuración opt-in push outbound', () => {
  beforeEach(() => vi.clearAllMocks());

  it('muestra máscara de write_api_key existente y la omite si no se escribe valor nuevo', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    vi.mocked(patch).mockResolvedValueOnce(BASE_CONECTOR);

    const conectorConWrite: ConectorInstancia = {
      ...BASE_CONECTOR,
      configuracion_publica: {
        ...BASE_CONECTOR.configuracion_publica,
        push_habilitado: true,
        push_modo_pago: 'borrador',
        write_user: 'writer@qa.com',
        tiene_write_api_key: true,
        diario_pagos_default_id: 7,
      },
    };

    renderWithProviders(<EditarConectorModal conector={conectorConWrite} onClose={onClose} />);

    const writeKeyInput = screen.getByLabelText(/Write API Key/i) as HTMLInputElement;
    expect(writeKeyInput.placeholder).toContain('Configurada — dejar vacío para mantener');
    expect(writeKeyInput.value).toBe('');

    await user.click(screen.getByRole('button', { name: /guardar cambios/i }));

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    const [, payload] = vi.mocked(patch).mock.calls[0];
    const cfgPayload = (payload as { configuracion: Record<string, unknown> }).configuracion;
    expect(cfgPayload.push_habilitado).toBe(true);
    expect(cfgPayload.write_user).toBe('writer@qa.com');
    expect(cfgPayload.diario_pagos_default_id).toBe(7);
    expect('write_api_key' in cfgPayload).toBe(false);
    expect('api_key' in cfgPayload).toBe(false);
  });

  it('envía write_api_key nueva y controles push al activar push_habilitado', async () => {
    const user = userEvent.setup();
    vi.mocked(patch).mockResolvedValueOnce(BASE_CONECTOR);

    renderWithProviders(<EditarConectorModal conector={BASE_CONECTOR} onClose={() => {}} />);

    await user.click(screen.getByRole('switch', { name: /habilitar push outbound/i }));
    fireEvent.change(screen.getByLabelText(/Usuario de escritura/i), {
      target: { value: 'writer@qa.com' },
    });
    fireEvent.change(screen.getByLabelText(/Write API Key/i), {
      target: { value: 'new-write-secret' },
    });
    fireEvent.change(screen.getByLabelText(/ID diario de pagos por defecto/i), {
      target: { value: '12' },
    });

    await user.click(screen.getByRole('button', { name: /guardar cambios/i }));

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    const [, payload] = vi.mocked(patch).mock.calls[0];
    const cfgPayload = (payload as { configuracion: Record<string, unknown> }).configuracion;
    expect(cfgPayload.push_habilitado).toBe(true);
    expect(cfgPayload.write_user).toBe('writer@qa.com');
    expect(cfgPayload.write_api_key).toBe('new-write-secret');
    expect(cfgPayload.diario_pagos_default_id).toBe(12);
  });

  it('muestra advertencia y deshabilita Guardar si write_user es asimétrico sin write_api_key', () => {
    renderWithProviders(<EditarConectorModal conector={BASE_CONECTOR} onClose={() => {}} />);

    fireEvent.change(screen.getByLabelText(/Usuario de escritura/i), {
      target: { value: 'solo-user@qa.com' },
    });

    expect(screen.getByText(/Configura tanto el usuario de escritura como la Write API Key/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /guardar cambios/i })).toBeDisabled();
  });
});

describe('ConectorDetallePage — dirección, Gestiones de Cobranza y Push Cobranza', () => {
  beforeEach(() => vi.clearAllMocks());

  function renderDetalle(conector: ConectorInstancia) {
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.includes('/jobs/')) {
        return Promise.resolve({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id_job: 'job-1',
              id_instancia: conector.id_conector,
              tipo_entidad: 'gestiones_cobranza',
              direccion: 'bidireccional',
              estado: 'completado',
              total_registros: 1,
              procesados: 1,
              creados: 1,
              actualizados: 0,
              omitidos: 0,
              fallidos: 0,
              iniciado_en: '2026-11-20T10:00:00Z',
              completado_en: '2026-11-20T10:00:02Z',
              duracion_segundos: 2,
            },
          ],
        });
      }
      return Promise.resolve(conector);
    });

    return renderWithProviders(
      <Routes>
        <Route path="/integraciones/conectores/:id" element={<ConectorDetallePage />} />
      </Routes>,
      `/integraciones/conectores/${conector.id_conector}`,
    );
  }

  it('deshabilita direcciones outbound/bidireccional y oculta Push Cobranza cuando push_habilitado=false', async () => {
    const user = userEvent.setup();
    renderDetalle(BASE_CONECTOR);

    expect(await screen.findByText('Odoo QA')).toBeInTheDocument();
    expect(screen.getAllByText('Gestiones de Cobranza').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByRole('button', { name: /push cobranza/i })).not.toBeInTheDocument();

    const dirSelect = screen.getByLabelText(/Dirección/i);
    await user.click(dirSelect);
    const listbox = await screen.findByRole('listbox');
    expect(within(listbox).getByRole('option', { name: /Exportación/i })).toHaveAttribute('aria-disabled', 'true');
    expect(within(listbox).getByRole('option', { name: /Bidireccional/i })).toHaveAttribute('aria-disabled', 'true');
  });

  it('habilita direcciones outbound/bidireccional y dispara Push Cobranza cuando push_habilitado=true', async () => {
    const user = userEvent.setup();
    vi.mocked(post).mockResolvedValue({
      mensaje: 'Push outbound de cobranza iniciado (pagos, gestiones_cobranza).',
      job_id: 'job-push-1',
      jobs: [],
    });

    const conectorPush: ConectorInstancia = {
      ...BASE_CONECTOR,
      configuracion_publica: {
        ...BASE_CONECTOR.configuracion_publica,
        push_habilitado: true,
        push_modo_pago: 'confirmado',
      },
    };
    renderDetalle(conectorPush);

    expect(await screen.findByText(/Habilitado \(confirmado\)/i)).toBeInTheDocument();
    const dirSelect = screen.getByLabelText(/Dirección/i);
    await user.click(dirSelect);
    const listbox = await screen.findByRole('listbox');
    expect(within(listbox).getByRole('option', { name: /Exportación/i })).not.toHaveAttribute('aria-disabled', 'true');
    await user.click(within(listbox).getByRole('option', { name: /Bidireccional/i }));

    const pushBtn = screen.getByRole('button', { name: /push cobranza/i });
    await user.click(pushBtn);

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/integration-hub/instancias/inst-odoo-1/push-cobranza/',
        { tipo: 'todos' },
      ),
    );
    expect(await screen.findByText(/Push outbound de cobranza iniciado/i)).toBeInTheDocument();
  });
});
