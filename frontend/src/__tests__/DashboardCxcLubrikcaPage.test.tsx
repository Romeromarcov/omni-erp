import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/cxcLubrikcaService', () => ({
  cxcLubrikcaService: {
    getResumen: vi.fn(),
    sincronizarPedidos: vi.fn(),
  },
}));

import { cxcLubrikcaService } from '../services/cxcLubrikcaService';
import DashboardCxcLubrikcaPage from '../pages/CxcLubrikca/DashboardCxcLubrikcaPage';

const resumen = {
  por_resultado: { verde: 5, amarillo: 2, rojo: 1 },
  total_conciliados: 8,
  total_facturados: 12,
  facturados_sin_conciliar: 4,
  pedidos_con_devolucion: 3,
  cartera_atascada: 6,
  bandejas_candidatas_sin_aprobar: 7,
  diferencia_total: '99.50',
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FeedbackProvider>
          <DashboardCxcLubrikcaPage />
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DashboardCxcLubrikcaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(cxcLubrikcaService.getResumen).mockResolvedValue(resumen);
  });

  afterEach(() => cleanup());

  it('muestra los KPIs del resumen de cartera', async () => {
    renderPage();
    expect(await screen.findByText('Conciliadas verde')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('Facturados sin conciliar')).toBeInTheDocument();
    expect(screen.getByText('Candidatas sin aprobar')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText(/99,50/)).toBeInTheDocument();
  });

  it('sincroniza con Odoo al pulsar el botón', async () => {
    vi.mocked(cxcLubrikcaService.sincronizarPedidos).mockResolvedValue({ pedidos: 3 });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Conciliadas verde');
    await user.click(screen.getByRole('button', { name: /sincronizar odoo/i }));
    await waitFor(() => {
      expect(cxcLubrikcaService.sincronizarPedidos).toHaveBeenCalled();
    });
    expect(await screen.findByText(/sincronización con odoo completada/i)).toBeInTheDocument();
  });

  it('muestra error si la sincronización falla', async () => {
    vi.mocked(cxcLubrikcaService.sincronizarPedidos).mockRejectedValue(
      new Error(JSON.stringify({ detail: 'Odoo no responde' })),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Conciliadas verde');
    await user.click(screen.getByRole('button', { name: /sincronizar odoo/i }));
    expect(await screen.findByText(/odoo no responde/i)).toBeInTheDocument();
  });
});
