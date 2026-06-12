/**
 * Regresión del crash de /integraciones: la página leía status.ultima_24h
 * (contrato inexistente) y reventaba con "Cannot read properties of
 * undefined (reading 'total')". Fija el contrato REAL del backend
 * (IntegrationHubStatusView: conectores{} + jobs_24h{}).
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import IntegrationHubPage from '../pages/Integraciones/IntegrationHubPage';
import * as svc from '../services/integrationHubService';

vi.mock('../services/integrationHubService', async (importOriginal) => {
  const real = await importOriginal<typeof import('../services/integrationHubService')>();
  return {
    ...real,
    getConectores: vi.fn(),
    getIntegrationHubStatus: vi.fn(),
  };
});

const mockedConectores = vi.mocked(svc.getConectores);
const mockedStatus = vi.mocked(svc.getIntegrationHubStatus);

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <IntegrationHubPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedConectores.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
});

describe('IntegrationHubPage — contrato real de /status/', () => {
  it('renderiza los KPIs con la forma real del backend sin crashear', async () => {
    mockedStatus.mockResolvedValue({
      conectores: { total: 3, activos: 2, con_error: 1, configurando: 0, inactivos: 0 },
      jobs_24h: { total: 14, completados: 11, con_errores: 1, fallidos: 2, en_progreso: 0 },
      proveedores_disponibles: ['odoo', 'google_sheets'],
    });
    renderPage();
    expect(await screen.findByText('Conectores activos')).toBeInTheDocument();
    expect(screen.getByText('14')).toBeInTheDocument();
    expect(screen.getByText('Fallidos')).toBeInTheDocument();
  });

  it('no revienta si el status llega incompleto (guard defensivo)', async () => {
    mockedStatus.mockResolvedValue({} as never);
    renderPage();
    expect(await screen.findByText('Sin conectores configurados')).toBeInTheDocument();
    expect(screen.queryByText('Jobs (24h)')).not.toBeInTheDocument();
  });
});
