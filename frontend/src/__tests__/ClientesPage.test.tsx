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

import { get, post, patch, del } from '../services/api';
import ClientesPage from '../pages/CRM/ClientesPage';

const clienteApi = {
  id_cliente: 'cli-1',
  id_empresa: 'e1',
  razon_social: 'ACME C.A.',
  nombre_comercial: 'ACME',
  rif: 'J-12345678',
  direccion: null,
  telefono: '04141234567',
  email: 'ventas@acme.com',
  tipo_cliente: 'CREDITO',
  limite_credito: '1000.00',
  dias_credito: 30,
  activo: true,
  contacto: null,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ClientesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ClientesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/crm/clientes/cli-1/credito-disponible')) {
        return Promise.resolve({
          credito_disponible: '700.00',
          limite_credito: '1000.00',
          saldo_pendiente: '300.00',
          bloqueado: false,
        });
      }
      if (url.startsWith('/crm/clientes/cli-1/historial-ventas')) {
        return Promise.resolve({ cliente_id: 'cli-1', pedidos: [] });
      }
      if (url.startsWith('/crm/contactos-cliente')) return Promise.resolve([]);
      if (url.startsWith('/crm/direcciones-cliente')) return Promise.resolve([]);
      if (url.startsWith('/crm/clientes')) return Promise.resolve([clienteApi]);
      return Promise.resolve([]);
    });
  });

  it('lista los clientes con su RIF y tipo', async () => {
    renderPage();
    expect(await screen.findByText('ACME C.A.')).toBeInTheDocument();
    expect(screen.getByText('J-12345678')).toBeInTheDocument();
    expect(screen.getByText('CREDITO')).toBeInTheDocument();
  });

  it('valida razón social y RIF requeridos al crear', async () => {
    renderPage();
    await screen.findByText('ACME C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }));
    expect(await screen.findByText('Nuevo cliente', { selector: 'h2' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete la razón social y el RIF/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un cliente de contado sin enviar límite/días de crédito', async () => {
    vi.mocked(post).mockResolvedValue({ id_cliente: 'cli-2' });
    renderPage();
    await screen.findByText('ACME C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }));
    fireEvent.change(await screen.findByLabelText(/Razón social/), {
      target: { value: 'Nuevo Cliente' },
    });
    fireEvent.change(screen.getByLabelText(/RIF/), { target: { value: 'V-99999999' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/crm/clientes/',
        expect.objectContaining({
          id_empresa: 'e1',
          razon_social: 'Nuevo Cliente',
          rif: 'V-99999999',
          tipo_cliente: 'CONTADO',
          limite_credito: '0',
          dias_credito: 0,
        }),
      ),
    );
  });

  it('editar un cliente envía el payload por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_cliente: 'cli-1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const razon = await screen.findByLabelText(/Razón social/);
    fireEvent.change(razon, { target: { value: 'ACME Editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/crm/clientes/cli-1/',
        expect.objectContaining({
          razon_social: 'ACME Editado',
          tipo_cliente: 'CREDITO',
          limite_credito: '1000.00',
          dias_credito: 30,
        }),
      ),
    );
  });

  it('eliminar un cliente pide confirmación y llama al servicio', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/crm/clientes/cli-1/'));
    confirmSpy.mockRestore();
  });

  it('no elimina si el usuario cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('abre el detalle y muestra el crédito disponible', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Detalle' }));
    expect(await screen.findByText('Crédito disponible')).toBeInTheDocument();
    expect(await screen.findByText(/Disponible: 700.00/)).toBeInTheDocument();
    expect(screen.getByText('Contactos')).toBeInTheDocument();
    expect(screen.getByText('Direcciones')).toBeInTheDocument();
  });
});
