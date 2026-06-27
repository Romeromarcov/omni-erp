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

import { get, post, del } from '../services/api';
import MovimientosInternosFondoPage from '../pages/Tesoreria/MovimientosInternosFondoPage';

const movimientoApi = {
  id: 1,
  caja_origen: 'c1',
  caja_destino: 'c2',
  monto: '100.00',
  fecha: '2026-06-27T10:00:00Z',
  descripcion: 'Traspaso a caja chica',
  id_moneda: 'm1',
  id_banco_origen: null,
  id_banco_destino: null,
  referencia_externa: null,
  usuario: null,
};

const cajaUno = { id_caja: 'c1', nombre: 'Caja Principal', moneda: 'm1', activa: true };
const cajaDos = { id_caja: 'c2', nombre: 'Caja Chica', moneda: 'm1', activa: true };
const monedaApi = { id_moneda: 'm1', nombre: 'Dólar', codigo_iso: 'USD' };

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/tesoreria/movimientos-internos-fondo/'))
      return Promise.resolve([movimientoApi]);
    if (url.startsWith('/finanzas/cajas/')) return Promise.resolve([cajaUno, cajaDos]);
    if (url.startsWith('/finanzas/monedas')) return Promise.resolve([monedaApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MovimientosInternosFondoPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('MovimientosInternosFondoPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista los movimientos resolviendo el nombre de las cajas', async () => {
    renderPage();
    expect(await screen.findByText('Traspaso a caja chica')).toBeInTheDocument();
    expect(screen.getByText('Caja Principal')).toBeInTheDocument();
    expect(screen.getByText('Caja Chica')).toBeInTheDocument();
  });

  it('valida origen/destino y monto requeridos al crear', async () => {
    renderPage();
    await screen.findByText('Traspaso a caja chica');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo movimiento' }));
    await screen.findByText('Nuevo movimiento interno', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Seleccione caja origen, caja destino/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('rechaza origen y destino iguales', async () => {
    renderPage();
    await screen.findByText('Traspaso a caja chica');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo movimiento' }));
    const dialog = within(await screen.findByRole('dialog'));

    fireEvent.mouseDown(dialog.getByLabelText(/Caja origen/));
    fireEvent.click(await screen.findByRole('option', { name: 'Caja Principal' }));
    fireEvent.mouseDown(dialog.getByLabelText(/Caja destino/));
    const opciones = await screen.findAllByRole('option', { name: 'Caja Principal' });
    fireEvent.click(opciones[0]);
    fireEvent.change(dialog.getByLabelText(/Monto/), { target: { value: '50' } });
    fireEvent.click(dialog.getByRole('button', { name: 'Guardar' }));

    expect(await screen.findByText(/deben ser distintas/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un movimiento con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id: 2 });
    renderPage();
    await screen.findByText('Traspaso a caja chica');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo movimiento' }));
    const dialog = within(await screen.findByRole('dialog'));

    fireEvent.mouseDown(dialog.getByLabelText(/Caja origen/));
    fireEvent.click(await screen.findByRole('option', { name: 'Caja Principal' }));
    fireEvent.mouseDown(dialog.getByLabelText(/Caja destino/));
    fireEvent.click(await screen.findByRole('option', { name: 'Caja Chica' }));
    fireEvent.change(dialog.getByLabelText(/Monto/), { target: { value: '75.50' } });
    fireEvent.mouseDown(dialog.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD/ }));
    fireEvent.change(dialog.getByLabelText(/Descripción/), {
      target: { value: 'reposición' },
    });
    fireEvent.click(dialog.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/tesoreria/movimientos-internos-fondo/',
        expect.objectContaining({
          caja_origen: 'c1',
          caja_destino: 'c2',
          monto: '75.50',
          id_moneda: 'm1',
          descripcion: 'reposición',
          referencia_externa: null,
        }),
      ),
    );
  });

  it('elimina un movimiento con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Traspaso a caja chica');
    const fila = screen.getByText('Traspaso a caja chica').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/tesoreria/movimientos-internos-fondo/1/'),
    );
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('Traspaso a caja chica');
    const fila = screen.getByText('Traspaso a caja chica').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
