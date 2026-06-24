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

import { get, post, patch, del } from '../services/api';
import GastosPage from '../pages/Gastos/GastosPage';

const gastoPendiente = {
  id_gasto: 'g1',
  id_empresa: 'e1',
  fecha_gasto: '2026-06-24',
  descripcion: 'Compra de papelería',
  monto: '100.00',
  monto_iva: '16.00',
  id_moneda: 'm1',
  id_categoria_gasto: 'cat-1',
  estado_gasto: 'PENDIENTE_APROBACION',
  estado_gasto_display: 'Pendiente Aprobación',
};

const gastoAprobado = {
  ...gastoPendiente,
  id_gasto: 'g2',
  descripcion: 'Servicio aprobado',
  estado_gasto: 'APROBADO',
  estado_gasto_display: 'Aprobado',
};

const categoriaApi = {
  id_categoria_gasto: 'cat-1',
  id_empresa: 'e1',
  nombre_categoria: 'Papelería',
  activo: true,
};

const monedaApi = { id_moneda: 'm1', nombre: 'Dólar', codigo_iso: 'USD' };
const cuentaApi = {
  id_cuenta_contable: 'cta-1',
  codigo_cuenta: '6.1.01',
  nombre_cuenta: 'Servicios básicos',
};

let gastosResult = [gastoPendiente, gastoAprobado];

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/gastos/categorias-gasto/activas')) return Promise.resolve([categoriaApi]);
    if (url.startsWith('/finanzas/monedas')) return Promise.resolve([monedaApi]);
    if (url.startsWith('/contabilidad/plan-cuentas')) return Promise.resolve([cuentaApi]);
    if (url.startsWith('/gastos/detalles-gasto')) return Promise.resolve([]);
    if (url.startsWith('/gastos/gastos')) return Promise.resolve(gastosResult);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <GastosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('GastosPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    gastosResult = [gastoPendiente, gastoAprobado];
    setupGet();
  });

  it('lista los gastos con categoría y estado', async () => {
    renderPage();
    expect(await screen.findByText('Compra de papelería')).toBeInTheDocument();
    expect(screen.getByText('Pendiente Aprobación')).toBeInTheDocument();
    expect(screen.getAllByText('Papelería').length).toBeGreaterThan(0);
  });

  it('filtra por estado y arma el querystring', async () => {
    renderPage();
    await screen.findByText('Compra de papelería');
    fireEvent.mouseDown(screen.getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'Aprobado' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/gastos/gastos/?empresa=e1&estado_gasto=APROBADO'),
    );
  });

  it('valida campos requeridos al crear', async () => {
    renderPage();
    await screen.findByText('Compra de papelería');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo gasto' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Complete categoría, moneda, descripción y monto/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un gasto con factura enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_gasto: 'g3' });
    renderPage();
    await screen.findByText('Compra de papelería');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo gasto' }));
    fireEvent.mouseDown(await screen.findByLabelText(/Categoría/));
    fireEvent.click(await screen.findByRole('option', { name: 'Papelería' }));
    fireEvent.change(screen.getByLabelText(/Descripción/), {
      target: { value: 'Tóner' },
    });
    fireEvent.change(screen.getByLabelText(/^Monto/), { target: { value: '200' } });
    fireEvent.mouseDown(screen.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD/ }));
    fireEvent.click(screen.getByLabelText(/Tiene factura/));
    fireEvent.change(await screen.findByLabelText(/Número de factura/), {
      target: { value: 'F-9' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/gastos/gastos/',
        expect.objectContaining({
          id_empresa: 'e1',
          descripcion: 'Tóner',
          monto: '200',
          id_categoria_gasto: 'cat-1',
          id_moneda: 'm1',
          tiene_factura: true,
          numero_factura: 'F-9',
        }),
      ),
    );
  });

  it('edita un gasto enviando el payload por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_gasto: 'g1' });
    renderPage();
    await screen.findByText('Compra de papelería');
    const fila = screen.getByText('Compra de papelería').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    const desc = await screen.findByLabelText(/Descripción/);
    fireEvent.change(desc, { target: { value: 'Papelería editada' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/gastos/gastos/g1/',
        expect.objectContaining({ descripcion: 'Papelería editada' }),
      ),
    );
  });

  it('aprueba un gasto pendiente con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ id_gasto: 'g1', estado_gasto: 'APROBADO' });
    renderPage();
    await screen.findByText('Compra de papelería');
    const fila = screen.getByText('Compra de papelería').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Aprobar' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/gastos/gastos/g1/aprobar/', {}));
    confirmSpy.mockRestore();
  });

  it('no aprueba si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('Compra de papelería');
    const fila = screen.getByText('Compra de papelería').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Aprobar' }));
    expect(post).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('rechaza un gasto pendiente con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ id_gasto: 'g1', estado_gasto: 'RECHAZADO' });
    renderPage();
    await screen.findByText('Compra de papelería');
    const fila = screen.getByText('Compra de papelería').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Rechazar' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/gastos/gastos/g1/rechazar/', {}));
    confirmSpy.mockRestore();
  });

  it('deshabilita Aprobar/Rechazar en un gasto no pendiente', async () => {
    renderPage();
    await screen.findByText('Servicio aprobado');
    const fila = screen.getByText('Servicio aprobado').closest('tr')!;
    expect(within(fila).getByRole('button', { name: 'Aprobar' })).toBeDisabled();
    expect(within(fila).getByRole('button', { name: 'Rechazar' })).toBeDisabled();
  });

  it('elimina un gasto con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Compra de papelería');
    const fila = screen.getByText('Compra de papelería').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/gastos/gastos/g1/'));
    confirmSpy.mockRestore();
  });

  it('abre el detalle y agrega una línea de imputación (gasto pendiente)', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_gasto: 'd1' });
    renderPage();
    await screen.findByText('Compra de papelería');
    const fila = screen.getByText('Compra de papelería').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    expect(await screen.findByText('Líneas de imputación contable')).toBeInTheDocument();

    fireEvent.mouseDown(await screen.findByLabelText(/Cuenta contable/));
    fireEvent.click(await screen.findByRole('option', { name: /Servicios básicos/ }));
    fireEvent.change(screen.getByLabelText('Monto'), { target: { value: '50' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar línea' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/gastos/detalles-gasto/',
        expect.objectContaining({ id_gasto: 'g1', id_cuenta_contable: 'cta-1', monto: '50' }),
      ),
    );
  });

  it('valida la línea de imputación (cuenta y monto requeridos)', async () => {
    renderPage();
    await screen.findByText('Compra de papelería');
    const fila = screen.getByText('Compra de papelería').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Agregar línea' }));
    expect(
      await screen.findByText(/Seleccione la cuenta contable e indique el monto/),
    ).toBeInTheDocument();
  });

  it('en gasto no pendiente el detalle bloquea la edición de líneas', async () => {
    renderPage();
    await screen.findByText('Servicio aprobado');
    const fila = screen.getByText('Servicio aprobado').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    expect(
      await screen.findByText(/sus líneas no se pueden modificar/),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Agregar línea' })).not.toBeInTheDocument();
  });

  it('muestra error al fallar la aprobación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ error: 'Falta respaldo.' })));
    renderPage();
    await screen.findByText('Compra de papelería');
    const fila = screen.getByText('Compra de papelería').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Aprobar' }));
    expect(await screen.findByText(/Falta respaldo/)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });
});
