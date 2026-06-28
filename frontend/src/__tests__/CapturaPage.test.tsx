import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/cxcLubrikcaService', () => ({
  cxcLubrikcaService: {
    listPedidos: vi.fn(),
    listPagos: vi.fn(),
    recalcularPedido: vi.fn(),
    registrarVinculacion: vi.fn(),
  },
}));

import { cxcLubrikcaService } from '../services/cxcLubrikcaService';
import CapturaPage from '../pages/CxcLubrikca/CapturaPage';

const pedido = {
  id: 'ped-1',
  so_id: 'SO-0001',
  cliente_externo_id: 'cli-9',
  cliente_nombre: 'Lubricantes del Sur',
  vendedor_email: null,
  fecha: '2026-06-01',
  fecha_entrega: '2026-06-05',
  monto_total: '500.00',
  lista_precios: null,
  es_primera_compra: false,
  facturada: false,
  factura_id: null,
  monto_facturado: '0.00',
  estado_entrega: 'pendiente',
  entregada_completa: false,
  tiene_devolucion: false,
  bandeja: { id: 'b1', total_motor: '480.00', candidata_a_cierre: true } as never,
};

const pago = {
  id: 'pago-1',
  pago_id: 'PG-1',
  cliente_externo_id: 'cli-9',
  monto: '480.00',
  moneda: 'USD',
  metodo_pago: 'zelle',
  fecha_pago: '2026-06-04',
  vendedor_email: null,
  vinculado: false,
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FeedbackProvider>
          <CapturaPage />
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CapturaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(cxcLubrikcaService.listPedidos).mockResolvedValue([pedido] as never);
    vi.mocked(cxcLubrikcaService.listPagos).mockResolvedValue([pago] as never);
  });

  afterEach(() => cleanup());

  it('lista los pedidos con su total motor', async () => {
    renderPage();
    expect(await screen.findByText('SO-0001')).toBeInTheDocument();
    expect(screen.getByText('Lubricantes del Sur')).toBeInTheDocument();
    expect(screen.getByText(/480,00/)).toBeInTheDocument();
  });

  it('recalcula un pedido', async () => {
    vi.mocked(cxcLubrikcaService.recalcularPedido).mockResolvedValue({ id: 'b1' } as never);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('SO-0001');
    await user.click(screen.getByRole('button', { name: /recalcular/i }));
    await waitFor(() => {
      expect(cxcLubrikcaService.recalcularPedido).toHaveBeenCalledWith('ped-1');
    });
    expect(await screen.findByText(/pedido recalculado/i)).toBeInTheDocument();
  });

  it('vincula un pago del mismo cliente', async () => {
    vi.mocked(cxcLubrikcaService.registrarVinculacion).mockResolvedValue({ id: 'v1' } as never);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('SO-0001');
    await user.click(screen.getByRole('button', { name: /vincular pago/i }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.type(dialog.getByLabelText(/monto aplicado/i), '480.00');
    await user.type(dialog.getByLabelText(/hora del pago/i), '2026-06-04T10:00');
    // selecciona el pago en el TextField select
    await user.click(dialog.getByLabelText(/^pago$/i));
    await user.click(await screen.findByRole('option', { name: /PG-1/ }));
    await user.click(dialog.getByRole('button', { name: /^vincular$/i }));
    await waitFor(() => {
      expect(cxcLubrikcaService.registrarVinculacion).toHaveBeenCalledWith(
        expect.objectContaining({
          pedido: 'ped-1',
          pago: 'pago-1',
          monto_aplicado: '480.00',
          hora_pago_confirmada: '2026-06-04T10:00',
        }),
      );
    });
  });

  it('muestra el error 400 de campo del backend en la vinculación', async () => {
    vi.mocked(cxcLubrikcaService.registrarVinculacion).mockRejectedValue(
      new Error(JSON.stringify({ monto_aplicado: ['Supera el saldo del pago.'] })),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('SO-0001');
    await user.click(screen.getByRole('button', { name: /vincular pago/i }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.type(dialog.getByLabelText(/monto aplicado/i), '999.00');
    await user.type(dialog.getByLabelText(/hora del pago/i), '2026-06-04T10:00');
    await user.click(dialog.getByLabelText(/^pago$/i));
    await user.click(await screen.findByRole('option', { name: /PG-1/ }));
    await user.click(dialog.getByRole('button', { name: /^vincular$/i }));
    expect(await screen.findByText(/supera el saldo del pago/i)).toBeInTheDocument();
  });
});
