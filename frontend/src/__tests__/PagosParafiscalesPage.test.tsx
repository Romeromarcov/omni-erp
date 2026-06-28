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

import { get, post } from '../services/api';
import PagosParafiscalesPage from '../pages/Fiscal/PagosParafiscalesPage';

const pagoPendiente = {
  id_pago_parafiscal: 'pp1',
  id_empresa: 'e1',
  contribucion: 'contrib-1',
  contribucion_codigo: 'IVSS',
  contribucion_nombre: 'Seguro Social',
  periodo_año: 2026,
  periodo_mes: 6,
  periodo: '2026-06',
  monto: '300.00',
  id_moneda: 'm1',
  moneda_codigo: 'USD',
  referencia: null,
  estado: 'pendiente',
  fecha_pago: null,
  id_pago: null,
};

const pagoPagado = {
  ...pagoPendiente,
  id_pago_parafiscal: 'pp2',
  contribucion_codigo: 'INCES',
  periodo: '2026-05',
  monto: '120.00',
  estado: 'pagado',
};

const monedaApi = { id_moneda: 'm1', nombre: 'Dólar', codigo_iso: 'USD' };
const metodoApi = {
  id: 'mpa-1',
  metodo_pago: 'mp-1',
  nombre: 'Transferencia',
  activa: true,
  nombre_metodo: 'Transferencia',
  monedas: [],
};
const cajaApi = { id_caja: 'c1', nombre: 'Caja Principal', moneda: 'm1', activa: true };

let pagosResult: unknown[] = [pagoPendiente, pagoPagado];

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/fiscal/pagos-parafiscales/')) return Promise.resolve(pagosResult);
    if (url.startsWith('/finanzas/monedas')) return Promise.resolve([monedaApi]);
    if (url.startsWith('/finanzas/metodos-pago-empresa-activas')) return Promise.resolve([metodoApi]);
    if (url.startsWith('/finanzas/cajas/')) return Promise.resolve([cajaApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PagosParafiscalesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PagosParafiscalesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    pagosResult = [pagoPendiente, pagoPagado];
    setupGet();
  });

  it('lista los pagos con contribución, período, monto y estado', async () => {
    renderPage();
    expect(await screen.findByText('IVSS')).toBeInTheDocument();
    expect(screen.getByText('2026-06')).toBeInTheDocument();
    expect(screen.getByText('300.00 USD')).toBeInTheDocument();
    expect(screen.getByText('Pendiente')).toBeInTheDocument();
    expect(screen.getByText('Pagado')).toBeInTheDocument();
  });

  it('filtra por estado y arma el querystring', async () => {
    renderPage();
    await screen.findByText('IVSS');
    fireEvent.mouseDown(screen.getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'Pagado' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/fiscal/pagos-parafiscales/?estado=pagado'),
    );
  });

  it('valida contribución, monto y moneda al declarar', async () => {
    renderPage();
    await screen.findByText('IVSS');
    fireEvent.click(screen.getByRole('button', { name: 'Declarar período' }));
    await screen.findByText('Declarar período parafiscal', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique la contribución, el monto/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('declara un período con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_pago_parafiscal: 'pp3' });
    renderPage();
    await screen.findByText('IVSS');
    fireEvent.click(screen.getByRole('button', { name: 'Declarar período' }));
    const dialog = within(await screen.findByRole('dialog'));

    fireEvent.change(dialog.getByLabelText(/Contribución/), { target: { value: 'contrib-9' } });
    fireEvent.change(dialog.getByLabelText(/Año/), { target: { value: '2026' } });
    fireEvent.change(dialog.getByLabelText(/Mes/), { target: { value: '7' } });
    fireEvent.change(dialog.getByLabelText(/Monto/), { target: { value: '450' } });
    fireEvent.mouseDown(dialog.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD/ }));
    fireEvent.click(dialog.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/fiscal/pagos-parafiscales/',
        expect.objectContaining({
          contribucion: 'contrib-9',
          periodo_año: 2026,
          periodo_mes: 7,
          monto: '450',
          id_moneda: 'm1',
        }),
      ),
    );
  });

  it('paga un pago pendiente desde caja con método de pago', async () => {
    vi.mocked(post).mockResolvedValue({ id_pago_parafiscal: 'pp1', estado: 'pagado' });
    renderPage();
    await screen.findByText('IVSS');
    const fila = screen.getByText('IVSS').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Pagar' }));

    const dialog = within(await screen.findByRole('dialog'));
    // Comboboxes del diálogo en orden: Método de pago, Origen de fondos, Caja.
    const combos = dialog.getAllByRole('combobox');
    fireEvent.mouseDown(combos[0]);
    fireEvent.click(await screen.findByRole('option', { name: 'Transferencia' }));
    await waitFor(() =>
      expect(screen.queryByRole('option', { name: 'Transferencia' })).not.toBeInTheDocument(),
    );
    // Origen "Caja" es el valor por defecto del formulario; abrimos el select de caja.
    fireEvent.mouseDown(combos[2]);
    fireEvent.click(await screen.findByRole('option', { name: 'Caja Principal' }));
    fireEvent.change(dialog.getByLabelText(/Referencia/), { target: { value: 'PL-1' } });
    fireEvent.click(dialog.getByRole('button', { name: 'Pagar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/fiscal/pagos-parafiscales/pp1/pagar/', {
        metodo_pago: 'mp-1',
        referencia: 'PL-1',
        caja: 'c1',
      }),
    );
  });

  it('valida el método de pago requerido al pagar', async () => {
    renderPage();
    await screen.findByText('IVSS');
    const fila = screen.getByText('IVSS').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Pagar' }));
    const dialog = within(await screen.findByRole('dialog'));
    fireEvent.click(dialog.getByRole('button', { name: 'Pagar' }));
    expect(await screen.findByText(/Seleccione el método de pago/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('anula un pago pendiente con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ id_pago_parafiscal: 'pp1', estado: 'anulado' });
    renderPage();
    await screen.findByText('IVSS');
    const fila = screen.getByText('IVSS').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Anular' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/fiscal/pagos-parafiscales/pp1/anular/', {}),
    );
    confirmSpy.mockRestore();
  });

  it('deshabilita Pagar/Anular en un pago ya pagado (gated por estado)', async () => {
    renderPage();
    await screen.findByText('INCES');
    const fila = screen.getByText('INCES').closest('tr')!;
    expect(within(fila).getByRole('button', { name: 'Pagar' })).toBeDisabled();
    expect(within(fila).getByRole('button', { name: 'Anular' })).toBeDisabled();
  });
});
