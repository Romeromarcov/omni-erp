import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/tesoreriaService', () => ({
  tesoreriaService: {
    getMovimientosBancariosPaginated: vi.fn(),
    getCuentasBancarias: vi.fn(),
    importarCsv: vi.fn(),
  },
}));

import { tesoreriaService } from '../services/tesoreriaService';
import MovimientosBancariosPage from '../pages/Tesoreria/MovimientosBancariosPage';

const cuenta = {
  id_cuenta_bancaria: 'cb-1',
  nombre_banco: 'Banco Uno',
  numero_cuenta: '0102-0001',
  activo: true,
};

const movimiento = {
  id: 'mov-1',
  id_empresa: 'emp-1',
  id_cuenta_bancaria: 'cb-1',
  fecha_mov: '2026-06-10',
  descripcion: 'Pago cliente ACME',
  tipo: 'CREDITO',
  monto: '1500.7500',
  referencia: 'REF-9',
  estado: 'PENDIENTE',
  id_pago_conciliado: null,
  origen: 'CSV',
  fecha_creacion: '2026-06-10T10:00:00Z',
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/tesoreria/movimientos-bancarios']}>
          <MovimientosBancariosPage />
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('MovimientosBancariosPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    vi.mocked(tesoreriaService.getMovimientosBancariosPaginated).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [movimiento],
    });
    vi.mocked(tesoreriaService.getCuentasBancarias).mockResolvedValue([cuenta]);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('lista los movimientos con monto formateado con decimal.js', async () => {
    renderPage();
    expect(await screen.findByText('Pago cliente ACME')).toBeInTheDocument();
    expect(screen.getByText('1500.75')).toBeInTheDocument();
    expect(screen.getByText('PENDIENTE')).toBeInTheDocument();
    expect(screen.getByText('Banco Uno 0102-0001')).toBeInTheDocument();
  });

  it('filtra por estado y reinicia la paginación', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Pago cliente ACME');

    await user.click(screen.getAllByLabelText(/Estado/)[0]);
    await user.click(await screen.findByRole('option', { name: 'CONCILIADO' }));

    await waitFor(() => {
      expect(tesoreriaService.getMovimientosBancariosPaginated).toHaveBeenCalledWith(1, 20, {
        cuenta: '',
        estado: 'CONCILIADO',
      });
    });
  });

  it('importa un CSV: cuenta + archivo → servicio con la empresa activa', async () => {
    vi.mocked(tesoreriaService.importarCsv).mockResolvedValue({ importados: 5, omitidos: 0 });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Pago cliente ACME');

    await user.click(screen.getByRole('button', { name: 'Importar CSV' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByLabelText(/Cuenta bancaria/));
    await user.click(await screen.findByRole('option', { name: /Banco Uno — 0102-0001/ }));

    const file = new File(['fecha,descripcion,tipo,monto,referencia\n'], 'extracto.csv', {
      type: 'text/csv',
    });
    await user.upload(screen.getByLabelText('Elegir archivo CSV'), file);
    await user.click(screen.getByRole('button', { name: 'Importar' }));

    await waitFor(() => {
      expect(tesoreriaService.importarCsv).toHaveBeenCalledWith('emp-1', 'cb-1', file);
    });
  });

  it('muestra el error del backend si el import falla', async () => {
    vi.mocked(tesoreriaService.importarCsv).mockRejectedValue(
      new Error(JSON.stringify({ error: 'Cuenta bancaria no encontrada.' })),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Pago cliente ACME');

    await user.click(screen.getByRole('button', { name: 'Importar CSV' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByLabelText(/Cuenta bancaria/));
    await user.click(await screen.findByRole('option', { name: /Banco Uno — 0102-0001/ }));
    const file = new File(['x'], 'extracto.csv', { type: 'text/csv' });
    await user.upload(screen.getByLabelText('Elegir archivo CSV'), file);
    await user.click(screen.getByRole('button', { name: 'Importar' }));

    expect(await screen.findByText('Cuenta bancaria no encontrada.')).toBeInTheDocument();
  });

  it('deshabilita Importar mientras falte cuenta o archivo', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Pago cliente ACME');
    await user.click(screen.getByRole('button', { name: 'Importar CSV' }));
    expect(screen.getByRole('button', { name: 'Importar' })).toBeDisabled();
  });
});
