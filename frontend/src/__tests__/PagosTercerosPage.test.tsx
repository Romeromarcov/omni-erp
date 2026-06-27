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
import PagosTercerosPage from '../pages/Finanzas/PagosTerceros/PagosTercerosPage';

const pagoPendiente = {
  id_pago_tercero: 'p1',
  id_empresa: 'e1',
  id_proveedor: null,
  proveedor_nombre: null,
  id_moneda: 'm1',
  moneda_codigo: 'USD',
  monto: '50.00',
  comision: null,
  referencia_zelle: 'Z-123',
  fecha: '2026-06-27',
  concepto: 'Cobro pendiente',
  estado: 'pendiente',
  id_abono_cxp: null,
  id_cxc_reintegro: null,
};

const pagoAnulado = {
  ...pagoPendiente,
  id_pago_tercero: 'p2',
  monto: '80.00',
  referencia_zelle: 'Z-999',
  concepto: 'Cobro anulado',
  estado: 'anulado',
};

const proveedorApi = {
  id_proveedor: 'prov-1',
  id_empresa: 'e1',
  razon_social: 'Proveedor Uno',
  rif: 'J-123',
};
const monedaApi = { id_moneda: 'm1', nombre: 'Dólar', codigo_iso: 'USD' };

let pagosResult: unknown[] = [pagoPendiente, pagoAnulado];

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/finanzas/pagos-terceros/')) return Promise.resolve(pagosResult);
    if (url.startsWith('/proveedores/proveedores/')) return Promise.resolve([proveedorApi]);
    if (url.startsWith('/finanzas/monedas')) return Promise.resolve([monedaApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PagosTercerosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PagosTercerosPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    pagosResult = [pagoPendiente, pagoAnulado];
    setupGet();
  });

  it('lista los pagos con monto, estado y proveedor sin asociar', async () => {
    renderPage();
    expect(await screen.findByText('50.00 USD')).toBeInTheDocument();
    expect(screen.getByText('Pendiente')).toBeInTheDocument();
    expect(screen.getByText('Anulado')).toBeInTheDocument();
    expect(screen.getAllByText('— (sin asociar)').length).toBeGreaterThan(0);
  });

  it('filtra por estado y arma el querystring', async () => {
    renderPage();
    await screen.findByText('Z-123');
    fireEvent.mouseDown(screen.getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'Abonado' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/finanzas/pagos-terceros/?estado=abonado'),
    );
  });

  it('valida moneda y monto requeridos al crear', async () => {
    renderPage();
    await screen.findByText('Z-123');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cobro' }));
    await screen.findByText('Nuevo cobro de tercero', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique la moneda y el monto/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un cobro con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_pago_tercero: 'p3' });
    renderPage();
    await screen.findByText('Z-123');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cobro' }));
    const dialog = within(await screen.findByRole('dialog'));

    fireEvent.change(dialog.getByLabelText(/Monto/), { target: { value: '120' } });
    fireEvent.mouseDown(dialog.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD/ }));
    fireEvent.change(dialog.getByLabelText(/Referencia Zelle/), { target: { value: 'Z-NEW' } });
    fireEvent.click(dialog.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/finanzas/pagos-terceros/',
        expect.objectContaining({
          id_proveedor: null,
          id_moneda: 'm1',
          monto: '120',
          referencia_zelle: 'Z-NEW',
          fecha: '2026-06-27',
        }),
      ),
    );
  });

  it('abona un pago pendiente con la CxP del prompt', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('cxp-77');
    vi.mocked(post).mockResolvedValue({ id_pago_tercero: 'p1', estado: 'abonado' });
    renderPage();
    await screen.findByText('Z-123');
    const fila = screen.getByText('Z-123').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Abonar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/finanzas/pagos-terceros/p1/abonar/', {
        cxp: 'cxp-77',
        descripcion: '',
      }),
    );
    promptSpy.mockRestore();
  });

  it('no abona si el prompt se cancela', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue(null);
    renderPage();
    await screen.findByText('Z-123');
    const fila = screen.getByText('Z-123').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Abonar' }));
    expect(post).not.toHaveBeenCalled();
    promptSpy.mockRestore();
  });

  it('solicita reintegro de un pago pendiente', async () => {
    vi.mocked(post).mockResolvedValue({ id_pago_tercero: 'p1', estado: 'reintegro_pendiente' });
    renderPage();
    await screen.findByText('Z-123');
    const fila = screen.getByText('Z-123').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Reintegro' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/finanzas/pagos-terceros/p1/solicitar-reintegro/', {}),
    );
  });

  it('anula un pago pendiente con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ id_pago_tercero: 'p1', estado: 'anulado' });
    renderPage();
    await screen.findByText('Z-123');
    const fila = screen.getByText('Z-123').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Anular' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/finanzas/pagos-terceros/p1/anular/', {}),
    );
    confirmSpy.mockRestore();
  });

  it('deshabilita las acciones de un pago anulado (gated por estado)', async () => {
    renderPage();
    await screen.findByText('Z-999');
    const fila = screen.getByText('Z-999').closest('tr')!;
    expect(within(fila).getByRole('button', { name: 'Abonar' })).toBeDisabled();
    expect(within(fila).getByRole('button', { name: 'Reintegro' })).toBeDisabled();
    expect(within(fila).getByRole('button', { name: 'Anular' })).toBeDisabled();
  });
});
