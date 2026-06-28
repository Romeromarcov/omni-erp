import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));
vi.mock('../services/monedas', () => ({ fetchMonedas: vi.fn() }));

import { get, post, patch, del } from '../services/api';
import { fetchMonedas } from '../services/monedas';
import CuentasBancariasEmpresaPage from '../pages/BancaElectronica/CuentasBancariasEmpresaPage';

const cuentaApi = {
  id: 'cta-1',
  empresa: 'e1',
  banco: 'Banco de Venezuela',
  numero_cuenta: '0102-0001',
  tipo_cuenta: 'corriente',
  moneda: 'mon-1',
  saldo_actual: '1500.00',
  activa: true,
  referencia_externa: null,
  documento_json: null,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CuentasBancariasEmpresaPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CuentasBancariasEmpresaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/banca-electronica/cuentas-bancarias-empresa')) {
        return Promise.resolve([cuentaApi]);
      }
      return Promise.resolve([]);
    });
    vi.mocked(fetchMonedas).mockResolvedValue([
      { id_moneda: 'mon-1', nombre: 'Dólar', codigo_iso: 'USD' },
    ]);
  });

  it('lista las cuentas con banco, número, tipo, moneda y saldo', async () => {
    renderPage();
    expect(await screen.findByText('Banco de Venezuela')).toBeInTheDocument();
    expect(screen.getByText('0102-0001')).toBeInTheDocument();
    expect(screen.getByText('Corriente')).toBeInTheDocument();
    expect(screen.getByText('USD')).toBeInTheDocument();
    expect(screen.getByText('1500.00')).toBeInTheDocument();
  });

  it('valida banco, número y moneda requeridos al crear', async () => {
    renderPage();
    await screen.findByText('Banco de Venezuela');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva cuenta' }));
    expect(await screen.findByText('Nueva cuenta', { selector: 'h2' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Complete el banco, el número de cuenta y la moneda/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una cuenta con el payload correcto', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'cta-2' });
    renderPage();
    await screen.findByText('Banco de Venezuela');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva cuenta' }));
    fireEvent.change(await screen.findByLabelText(/Banco/), {
      target: { value: 'Banesco' },
    });
    fireEvent.change(screen.getByLabelText(/Número de cuenta/), {
      target: { value: '0134-9999' },
    });
    fireEvent.mouseDown(screen.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD — Dólar/ }));
    fireEvent.change(screen.getByLabelText(/Saldo actual/), { target: { value: '250.50' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/banca-electronica/cuentas-bancarias-empresa/',
        expect.objectContaining({
          empresa: 'e1',
          banco: 'Banesco',
          numero_cuenta: '0134-9999',
          tipo_cuenta: 'corriente',
          moneda: 'mon-1',
          saldo_actual: '250.50',
          activa: true,
        }),
      ),
    );
  });

  it('crea una cuenta de ahorro y la marca inactiva', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'cta-3' });
    renderPage();
    await screen.findByText('Banco de Venezuela');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva cuenta' }));
    fireEvent.change(await screen.findByLabelText(/Banco/), { target: { value: 'Mercantil' } });
    fireEvent.change(screen.getByLabelText(/Número de cuenta/), { target: { value: '0105-1' } });
    fireEvent.mouseDown(screen.getByLabelText(/Tipo de cuenta/));
    fireEvent.click(await screen.findByRole('option', { name: 'Ahorro' }));
    fireEvent.mouseDown(screen.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD — Dólar/ }));
    fireEvent.click(screen.getByLabelText('Activa'));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/banca-electronica/cuentas-bancarias-empresa/',
        expect.objectContaining({ tipo_cuenta: 'ahorro', activa: false }),
      ),
    );
  });

  it('editar una cuenta envía el payload por id (precarga el formulario)', async () => {
    vi.mocked(patch).mockResolvedValue({ id: 'cta-1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const banco = (await screen.findByLabelText(/Banco/)) as HTMLInputElement;
    await waitFor(() => expect(banco.value).toBe('Banco de Venezuela'));
    fireEvent.change(banco, { target: { value: 'BdV Editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/banca-electronica/cuentas-bancarias-empresa/cta-1/',
        expect.objectContaining({
          banco: 'BdV Editado',
          numero_cuenta: '0102-0001',
          moneda: 'mon-1',
          tipo_cuenta: 'corriente',
        }),
      ),
    );
  });

  it('eliminar una cuenta pide confirmación y llama al servicio', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/banca-electronica/cuentas-bancarias-empresa/cta-1/'),
    );
    confirmSpy.mockRestore();
  });

  it('no elimina si el usuario cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('cierra el diálogo con Cancelar', async () => {
    renderPage();
    await screen.findByText('Banco de Venezuela');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva cuenta' }));
    await screen.findByText('Nueva cuenta', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await waitFor(() =>
      expect(screen.queryByText('Nueva cuenta', { selector: 'h2' })).not.toBeInTheDocument(),
    );
  });

  it('muestra error al fallar el guardado (mensajeDeError)', async () => {
    vi.mocked(post).mockRejectedValue(
      new Error(JSON.stringify({ numero_cuenta: ['Ya existe.'] })),
    );
    renderPage();
    await screen.findByText('Banco de Venezuela');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva cuenta' }));
    fireEvent.change(await screen.findByLabelText(/Banco/), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText(/Número de cuenta/), { target: { value: '1' } });
    fireEvent.mouseDown(screen.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD — Dólar/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/numero_cuenta: Ya existe\./)).toBeInTheDocument();
  });
});
