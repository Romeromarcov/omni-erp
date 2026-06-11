import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/cuentasPorCobrarService', () => ({
  cuentasPorCobrarService: {
    getAllPaginated: vi.fn(),
    crearAbono: vi.fn(),
  },
}));

import { cuentasPorCobrarService } from '../services/cuentasPorCobrarService';
import CuentasPorCobrarPage from '../pages/CxC/CuentasPorCobrarPage';

const mockCuentas = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      empresa: 'emp-001',
      cliente: 'cli-001',
      cliente_nombre: 'Cliente Alfa C.A.',
      cliente_ref: null,
      monto: '350.00',
      saldo_pendiente: '200.00',
      fecha_emision: '2026-06-01',
      fecha_vencimiento: '2026-07-01',
      estado: 'parcial',
      descripcion: 'Pedido P-0001',
    },
    {
      id: 2,
      empresa: 'emp-001',
      cliente: null,
      cliente_nombre: 'Cliente Beta',
      cliente_ref: 'odoo-9',
      monto: '100.00',
      saldo_pendiente: '0.00',
      fecha_emision: '2026-05-01',
      fecha_vencimiento: '2026-06-01',
      estado: 'pagada',
      descripcion: null,
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FeedbackProvider>
          <CuentasPorCobrarPage />
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CuentasPorCobrarPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(cuentasPorCobrarService.getAllPaginated).mockResolvedValue(mockCuentas);
  });

  afterEach(() => {
    cleanup();
  });

  it('lista las cuentas por cobrar con cliente y saldo', async () => {
    renderPage();
    expect(await screen.findByText('Cliente Alfa C.A.')).toBeInTheDocument();
    expect(screen.getByText('Cliente Beta')).toBeInTheDocument();
    expect(screen.getByText(/200,00/)).toBeInTheDocument();
  });

  it('deshabilita "Abonar" para cuentas pagadas o sin saldo', async () => {
    renderPage();
    await screen.findByText('Cliente Alfa C.A.');
    const botones = screen.getAllByRole('button', { name: /abonar/i });
    expect(botones[0]).toBeEnabled();
    expect(botones[1]).toBeDisabled();
  });

  it('valida el monto con zod antes de enviar (monto vacío)', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Cliente Alfa C.A.');
    await user.click(screen.getAllByRole('button', { name: /abonar/i })[0]);
    await user.click(await screen.findByRole('button', { name: /registrar abono/i }));
    expect(await screen.findByText(/el monto es obligatorio/i)).toBeInTheDocument();
    expect(cuentasPorCobrarService.crearAbono).not.toHaveBeenCalled();
  });

  it('valida que el monto sea un decimal mayor a 0', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Cliente Alfa C.A.');
    await user.click(screen.getAllByRole('button', { name: /abonar/i })[0]);
    await user.type(screen.getByLabelText(/monto/i), '-5');
    await user.click(screen.getByRole('button', { name: /registrar abono/i }));
    expect(await screen.findByText(/mayor a 0/i)).toBeInTheDocument();
    expect(cuentasPorCobrarService.crearAbono).not.toHaveBeenCalled();
  });

  it('envía el abono con el contrato P0-2 (cuenta_por_cobrar, monto, descripcion)', async () => {
    vi.mocked(cuentasPorCobrarService.crearAbono).mockResolvedValue({
      id: 10,
      cuenta_por_cobrar: 1,
      monto: '150.00',
      descripcion: 'Pago parcial',
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Cliente Alfa C.A.');
    await user.click(screen.getAllByRole('button', { name: /abonar/i })[0]);
    await user.type(screen.getByLabelText(/monto/i), '150.00');
    await user.type(screen.getByLabelText(/descripción/i), 'Pago parcial');
    await user.click(screen.getByRole('button', { name: /registrar abono/i }));

    await waitFor(() => {
      expect(cuentasPorCobrarService.crearAbono).toHaveBeenCalledWith({
        cuenta_por_cobrar: 1,
        monto: '150.00',
        descripcion: 'Pago parcial',
      });
    });
    // El modal se cierra y la lista se invalida
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /registrar abono/i })).not.toBeInTheDocument();
    });
  });

  it('muestra el error 400 del backend sobre el campo monto', async () => {
    vi.mocked(cuentasPorCobrarService.crearAbono).mockRejectedValue(
      new Error(JSON.stringify({ monto: ['El abono (500.00) supera el saldo pendiente (200.00).'] }))
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Cliente Alfa C.A.');
    await user.click(screen.getAllByRole('button', { name: /abonar/i })[0]);
    await user.type(screen.getByLabelText(/monto/i), '500.00');
    await user.click(screen.getByRole('button', { name: /registrar abono/i }));
    expect(await screen.findByText(/supera el saldo pendiente/i)).toBeInTheDocument();
  });

  it('muestra mensaje vacío cuando no hay cuentas', async () => {
    vi.mocked(cuentasPorCobrarService.getAllPaginated).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    renderPage();
    expect(await screen.findByText(/no hay cuentas por cobrar/i)).toBeInTheDocument();
  });
});
