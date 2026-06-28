import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/cxcLubrikcaService', () => ({
  cxcLubrikcaService: {
    listConciliaciones: vi.fn(),
    getResumen: vi.fn(),
    listPedidos: vi.fn(),
    conciliar: vi.fn(),
    revisarConciliacion: vi.fn(),
  },
}));

import { cxcLubrikcaService } from '../services/cxcLubrikcaService';
import ConciliacionPage from '../pages/CxcLubrikca/ConciliacionPage';

const conciliacion = {
  id: 'c1',
  pedido: 'SO-0001',
  total_motor: '480.00',
  monto_facturado: '480.00',
  ncs: '0.00',
  diferencia: '0.00',
  resultado: 'verde',
  revisado_por: null,
  conciliado_en: '2026-06-06T10:00:00Z',
};

const conciliacionRoja = {
  ...conciliacion,
  id: 'c2',
  pedido: 'SO-0002',
  diferencia: '15.00',
  resultado: 'rojo',
  revisado_por: 5,
};

const resumen = {
  por_resultado: { verde: 1, amarillo: 0, rojo: 1 },
  total_conciliados: 2,
  total_facturados: 3,
  facturados_sin_conciliar: 1,
  pedidos_con_devolucion: 0,
  cartera_atascada: 0,
  bandejas_candidatas_sin_aprobar: 0,
  diferencia_total: '15.00',
};

const pedidoFacturado = {
  id: 'ped-1',
  so_id: 'SO-0003',
  cliente_externo_id: 'cli-1',
  cliente_nombre: 'Cliente C',
  vendedor_email: null,
  fecha: '2026-06-01',
  fecha_entrega: '2026-06-02',
  monto_total: '300.00',
  lista_precios: null,
  es_primera_compra: false,
  facturada: true,
  factura_id: 'f1',
  monto_facturado: '300.00',
  estado_entrega: 'entregada',
  entregada_completa: true,
  tiene_devolucion: false,
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FeedbackProvider>
          <ConciliacionPage />
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ConciliacionPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(cxcLubrikcaService.listConciliaciones).mockResolvedValue([
      conciliacion,
      conciliacionRoja,
    ] as never);
    vi.mocked(cxcLubrikcaService.getResumen).mockResolvedValue(resumen);
    vi.mocked(cxcLubrikcaService.listPedidos).mockResolvedValue([pedidoFacturado] as never);
  });

  afterEach(() => cleanup());

  it('lista las conciliaciones y las KPIs del resumen', async () => {
    renderPage();
    expect(await screen.findByText('SO-0001')).toBeInTheDocument();
    expect(screen.getByText('SO-0002')).toBeInTheDocument();
    expect(screen.getByText('Facturados sin conciliar')).toBeInTheDocument();
  });

  it('marca una conciliación como revisada', async () => {
    vi.mocked(cxcLubrikcaService.revisarConciliacion).mockResolvedValue(conciliacion as never);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('SO-0001');
    await user.click(screen.getByRole('button', { name: /marcar revisado/i }));
    await waitFor(() => {
      expect(cxcLubrikcaService.revisarConciliacion).toHaveBeenCalledWith('c1');
    });
    expect(await screen.findByText(/marcada como revisada/i)).toBeInTheDocument();
  });

  it('deshabilita "Marcar revisado" si ya fue revisada', async () => {
    renderPage();
    await screen.findByText('SO-0002');
    expect(screen.getByRole('button', { name: /^revisado$/i })).toBeDisabled();
  });

  it('concilia un pedido facturado', async () => {
    vi.mocked(cxcLubrikcaService.conciliar).mockResolvedValue(conciliacion as never);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('SO-0001');
    await user.click(screen.getByRole('button', { name: /conciliar pedido/i }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByLabelText(/pedido facturado/i));
    await user.click(await screen.findByRole('option', { name: /SO-0003/ }));
    await user.click(dialog.getByRole('button', { name: /^conciliar$/i }));
    await waitFor(() => {
      expect(cxcLubrikcaService.conciliar).toHaveBeenCalledWith({ pedido: 'ped-1' });
    });
  });

  it('muestra el error general del backend al conciliar', async () => {
    vi.mocked(cxcLubrikcaService.conciliar).mockRejectedValue(
      new Error(JSON.stringify({ detail: 'El pedido no está facturado.' })),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('SO-0001');
    await user.click(screen.getByRole('button', { name: /conciliar pedido/i }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByLabelText(/pedido facturado/i));
    await user.click(await screen.findByRole('option', { name: /SO-0003/ }));
    await user.click(dialog.getByRole('button', { name: /^conciliar$/i }));
    expect(await screen.findByText(/el pedido no está facturado/i)).toBeInTheDocument();
  });
});
