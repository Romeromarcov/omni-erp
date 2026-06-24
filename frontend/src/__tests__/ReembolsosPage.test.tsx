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
import ReembolsosPage from '../pages/Gastos/ReembolsosPage';

const reembolsoPendiente = {
  id_reembolso: 'r1',
  id_empresa: 'e1',
  id_gasto: 'g1',
  monto_reembolso: '100.00',
  fecha_reembolso: '2026-06-24',
  id_moneda: 'm1',
  id_metodo_pago: 'mp1',
  estado_reembolso: 'PENDIENTE',
};

const reembolsoPagado = {
  ...reembolsoPendiente,
  id_reembolso: 'r2',
  estado_reembolso: 'PAGADO',
};

const gastoAprobado = {
  id_gasto: 'g1',
  descripcion: 'Servicio aprobado',
  monto: '100.00',
  estado_gasto: 'APROBADO',
};

const monedaApi = { id_moneda: 'm1', nombre: 'Dólar', codigo_iso: 'USD' };
const metodoApi = { id: 'link-1', metodo_pago: 'mp1', nombre: 'Transferencia', monedas: ['m1'] };

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/gastos/gastos')) return Promise.resolve([gastoAprobado]);
    if (url.startsWith('/finanzas/monedas')) return Promise.resolve([monedaApi]);
    if (url.startsWith('/finanzas/metodos-pago-empresa-activas'))
      return Promise.resolve([metodoApi]);
    if (url.startsWith('/gastos/reembolsos-gasto'))
      return Promise.resolve([reembolsoPendiente, reembolsoPagado]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ReembolsosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ReembolsosPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista reembolsos con la descripción del gasto y estado', async () => {
    renderPage();
    expect(await screen.findAllByText('Servicio aprobado')).toBeTruthy();
    expect(screen.getByText('PENDIENTE')).toBeInTheDocument();
    expect(screen.getByText('PAGADO')).toBeInTheDocument();
  });

  it('filtra por estado armando el querystring', async () => {
    renderPage();
    await screen.findByText('PENDIENTE');
    fireEvent.mouseDown(screen.getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'Pagado' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        '/gastos/reembolsos-gasto/?empresa=e1&estado_reembolso=PAGADO',
      ),
    );
  });

  it('valida campos requeridos al crear', async () => {
    renderPage();
    await screen.findByText('PENDIENTE');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo reembolso' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Complete gasto, monto, moneda y método de pago/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un reembolso usando el id real del método de pago', async () => {
    vi.mocked(post).mockResolvedValue({ id_reembolso: 'r3' });
    renderPage();
    await screen.findByText('PENDIENTE');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo reembolso' }));
    fireEvent.mouseDown(await screen.findByLabelText(/Gasto aprobado/));
    fireEvent.click(await screen.findByRole('option', { name: /Servicio aprobado/ }));
    fireEvent.change(screen.getByLabelText(/Monto a reembolsar/), { target: { value: '100' } });
    fireEvent.mouseDown(screen.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD/ }));
    fireEvent.mouseDown(screen.getByLabelText(/Método de pago/));
    fireEvent.click(await screen.findByRole('option', { name: 'Transferencia' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/gastos/reembolsos-gasto/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_gasto: 'g1',
          monto_reembolso: '100',
          id_moneda: 'm1',
          id_metodo_pago: 'mp1',
          estado_reembolso: 'PENDIENTE',
        }),
      ),
    );
  });

  it('procesa el pago de un reembolso pendiente con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ id_reembolso: 'r1', estado_reembolso: 'PAGADO' });
    renderPage();
    await screen.findByText('PENDIENTE');
    const fila = screen.getByText('PENDIENTE').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Procesar pago' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/gastos/reembolsos-gasto/r1/procesar_pago/', {}),
    );
    confirmSpy.mockRestore();
  });

  it('anula un reembolso pendiente con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ id_reembolso: 'r1', estado_reembolso: 'ANULADO' });
    renderPage();
    await screen.findByText('PENDIENTE');
    const fila = screen.getByText('PENDIENTE').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Anular' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/gastos/reembolsos-gasto/r1/anular/', {}),
    );
    confirmSpy.mockRestore();
  });

  it('no procesa si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('PENDIENTE');
    const fila = screen.getByText('PENDIENTE').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Procesar pago' }));
    expect(post).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('deshabilita acciones en un reembolso ya pagado', async () => {
    renderPage();
    await screen.findByText('PAGADO');
    const fila = screen.getByText('PAGADO').closest('tr')!;
    expect(within(fila).getByRole('button', { name: 'Procesar pago' })).toBeDisabled();
    expect(within(fila).getByRole('button', { name: 'Anular' })).toBeDisabled();
  });

  it('muestra error al fallar el procesado del pago', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ error: 'No procesable.' })));
    renderPage();
    await screen.findByText('PENDIENTE');
    const fila = screen.getByText('PENDIENTE').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Procesar pago' }));
    expect(await screen.findByText(/No procesable/)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it('del no se usa: las acciones son por workflow (sanity de imports)', () => {
    expect(del).toBeDefined();
  });
});
