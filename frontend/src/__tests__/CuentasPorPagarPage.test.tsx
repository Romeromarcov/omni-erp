import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/cuentasPorPagarService', () => ({
  cuentasPorPagarService: {
    getAllPaginated: vi.fn(),
    getAging: vi.fn(),
    abonar: vi.fn(),
  },
}));

import { cuentasPorPagarService } from '../services/cuentasPorPagarService';
import CuentasPorPagarPage from '../pages/Compras/CuentasPorPagarPage';

const cxpPendiente = {
  id_cxp: 'cxp-1111',
  id_empresa: 'emp-1',
  id_proveedor: 'prov-1',
  id_factura_compra: 'fac-1',
  referencia_externa: 'FAC-001',
  monto_total: '255.2000',
  monto_pendiente: '100.0000',
  fecha_emision: '2026-06-01',
  fecha_vencimiento: '2026-07-01',
  estado: 'PARCIAL',
  observaciones: null,
  activo: true,
  fecha_creacion: '2026-06-01T10:00:00Z',
};

const cxpPagada = {
  ...cxpPendiente,
  id_cxp: 'cxp-2222',
  referencia_externa: 'FAC-002',
  monto_pendiente: '0.0000',
  estado: 'PAGADA',
};

const pagina = { count: 2, next: null, previous: null, results: [cxpPendiente, cxpPagada] };

const aging = {
  empresa_id: 'emp-1',
  corriente: { monto: '60.00', cantidad: 1 },
  dias_1_30: { monto: '40.00', cantidad: 1 },
  dias_31_60: { monto: '0', cantidad: 0 },
  dias_61_90: { monto: '0', cantidad: 0 },
  dias_90_mas: { monto: '0', cantidad: 0 },
  total_general: '100.00',
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/compras/cuentas-por-pagar']}>
          <CuentasPorPagarPage />
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('CuentasPorPagarPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    vi.mocked(cuentasPorPagarService.getAllPaginated).mockResolvedValue(pagina);
    vi.mocked(cuentasPorPagarService.getAging).mockResolvedValue(aging);
    vi.mocked(cuentasPorPagarService.abonar).mockResolvedValue({
      abono_id: 'ab-1',
      cxp_id: 'cxp-1111',
      monto_abonado: '50.00',
      monto_pendiente: '50.0000',
      estado_cxp: 'PARCIAL',
    });
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('lista las CxP con saldos Decimal y estado, y muestra el aging', async () => {
    renderPage();
    expect(await screen.findByText('FAC-001')).toBeInTheDocument();
    expect(screen.getByText('100.00')).toBeInTheDocument();
    expect(screen.getByText('PARCIAL')).toBeInTheDocument();
    expect(screen.getByText('PAGADA')).toBeInTheDocument();
    // Panel de aging con buckets y total.
    expect(screen.getByText(/antigüedad de saldos/i)).toBeInTheDocument();
    expect(screen.getByText('60.00')).toBeInTheDocument();
    expect(screen.getByText(/1–30 días/)).toBeInTheDocument();
  });

  it('deshabilita Abonar para CxP pagadas o sin saldo', async () => {
    renderPage();
    await screen.findByText('FAC-001');
    const botones = screen.getAllByRole('button', { name: /^abonar$/i });
    expect(botones[0]).toBeEnabled();
    expect(botones[1]).toBeDisabled();
  });

  it('registra el abono con Idempotency-Key y reúsa la clave en el retry del mismo intento', async () => {
    const user = userEvent.setup();
    vi.mocked(cuentasPorPagarService.abonar)
      .mockRejectedValueOnce(new Error(JSON.stringify({ detail: 'Timeout temporal.' })))
      .mockResolvedValueOnce({
        abono_id: 'ab-1',
        cxp_id: 'cxp-1111',
        monto_abonado: '50.00',
        monto_pendiente: '50.0000',
        estado_cxp: 'PARCIAL',
      });
    renderPage();
    await screen.findByText('FAC-001');

    await user.click(screen.getAllByRole('button', { name: /^abonar$/i })[0]);
    await user.type(await screen.findByLabelText(/monto/i), '50.00');
    await user.click(screen.getByRole('button', { name: /registrar abono/i }));
    expect(await screen.findByText('Timeout temporal.')).toBeInTheDocument();

    // Retry del MISMO intento (mismo payload) → misma Idempotency-Key.
    await user.click(screen.getByRole('button', { name: /registrar abono/i }));
    await waitFor(() => expect(cuentasPorPagarService.abonar).toHaveBeenCalledTimes(2));

    const llamadas = vi.mocked(cuentasPorPagarService.abonar).mock.calls;
    expect(llamadas[0][0]).toBe('cxp-1111');
    expect(llamadas[0][1]).toEqual({ monto: '50.00', descripcion: '' });
    expect(llamadas[0][2]).toBeTruthy();
    expect(llamadas[1][2]).toBe(llamadas[0][2]);
  });

  it('genera una clave nueva si cambia el payload del abono', async () => {
    const user = userEvent.setup();
    vi.mocked(cuentasPorPagarService.abonar)
      .mockRejectedValueOnce(new Error(JSON.stringify({ detail: 'Falla transitoria.' })))
      .mockResolvedValueOnce({
        abono_id: 'ab-2',
        cxp_id: 'cxp-1111',
        monto_abonado: '60.00',
        monto_pendiente: '40.0000',
        estado_cxp: 'PARCIAL',
      });
    renderPage();
    await screen.findByText('FAC-001');

    await user.click(screen.getAllByRole('button', { name: /^abonar$/i })[0]);
    const inputMonto = await screen.findByLabelText(/monto/i);
    await user.type(inputMonto, '50.00');
    await user.click(screen.getByRole('button', { name: /registrar abono/i }));
    await screen.findByText('Falla transitoria.');

    // Operación distinta (otro monto) → clave nueva.
    await user.clear(inputMonto);
    await user.type(inputMonto, '60.00');
    await user.click(screen.getByRole('button', { name: /registrar abono/i }));
    await waitFor(() => expect(cuentasPorPagarService.abonar).toHaveBeenCalledTimes(2));

    const llamadas = vi.mocked(cuentasPorPagarService.abonar).mock.calls;
    expect(llamadas[1][2]).not.toBe(llamadas[0][2]);
  });

  it('muestra el 400 de campo del backend (monto > saldo) en el formulario', async () => {
    const user = userEvent.setup();
    vi.mocked(cuentasPorPagarService.abonar).mockRejectedValue(
      new Error(JSON.stringify({ monto: ['El abono excede el saldo pendiente.'] })),
    );
    renderPage();
    await screen.findByText('FAC-001');
    await user.click(screen.getAllByRole('button', { name: /^abonar$/i })[0]);
    await user.type(await screen.findByLabelText(/monto/i), '999');
    await user.click(screen.getByRole('button', { name: /registrar abono/i }));
    expect(await screen.findByText('El abono excede el saldo pendiente.')).toBeInTheDocument();
  });

  it('valida con zod que el monto sea un decimal positivo', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('FAC-001');
    await user.click(screen.getAllByRole('button', { name: /^abonar$/i })[0]);
    await user.type(await screen.findByLabelText(/monto/i), 'abc');
    await user.click(screen.getByRole('button', { name: /registrar abono/i }));
    expect(await screen.findByText(/el monto debe ser un número mayor a 0/i)).toBeInTheDocument();
    expect(cuentasPorPagarService.abonar).not.toHaveBeenCalled();
  });

  it('filtra por estado y resetea la página', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('FAC-001');
    await user.click(screen.getByLabelText(/filtrar por estado/i));
    await user.click(await screen.findByRole('option', { name: 'VENCIDA' }));
    await waitFor(() =>
      expect(cuentasPorPagarService.getAllPaginated).toHaveBeenCalledWith(1, 20, {
        estado: 'VENCIDA',
      }),
    );
  });
});
