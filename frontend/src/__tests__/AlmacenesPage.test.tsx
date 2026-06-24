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
import { almacenesService } from '../services/almacenesService';
import AlmacenesPage from '../pages/Inventario/AlmacenesPage';

const almacenApi = {
  id_almacen: 'alm-1',
  nombre_almacen: 'Central',
  codigo_almacen: 'CEN',
  direccion: 'Av. Principal',
  activo: true,
  id_empresa: 'e1',
};

describe('almacenesService CRUD escritura', () => {
  beforeEach(() => vi.clearAllMocks());

  const payload = {
    id_empresa: 'e1',
    nombre_almacen: 'Sur',
    codigo_almacen: 'SUR',
    direccion: null,
  };

  it('getAll normaliza la lista paginada', async () => {
    vi.mocked(get).mockResolvedValue({ results: [almacenApi], count: 1 });
    expect(await almacenesService.getAll()).toEqual([almacenApi]);
    expect(get).toHaveBeenCalledWith('/almacenes/almacenes/');
  });

  it('create postea al endpoint de almacenes', async () => {
    vi.mocked(post).mockResolvedValue({ id_almacen: 'a2' });
    await almacenesService.create(payload);
    expect(post).toHaveBeenCalledWith('/almacenes/almacenes/', payload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_almacen: 'a2' });
    await almacenesService.update('a2', payload);
    expect(patch).toHaveBeenCalledWith('/almacenes/almacenes/a2/', payload);
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    await almacenesService.remove('a2');
    expect(del).toHaveBeenCalledWith('/almacenes/almacenes/a2/');
  });
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AlmacenesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AlmacenesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockResolvedValue([almacenApi]);
  });

  it('lista almacenes y enlaza a la configuración de pasos', async () => {
    renderPage();
    expect(await screen.findByText('Central')).toBeInTheDocument();
    expect(screen.getByText('Av. Principal')).toBeInTheDocument();
    const pasos = screen.getByRole('link', { name: /Pasos/ });
    expect(pasos).toHaveAttribute('href', '/inventario/pasos-operacion?almacen=alm-1');
  });

  it('valida campos requeridos al crear', async () => {
    renderPage();
    await screen.findByText('Central');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo almacén' }));
    expect(await screen.findByText('Nuevo almacén', { selector: 'h2' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete nombre y código/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('editar un almacén envía el payload con whitelist', async () => {
    vi.mocked(patch).mockResolvedValue({ id_almacen: 'alm-1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const nombre = await screen.findByLabelText(/Nombre/);
    fireEvent.change(nombre, { target: { value: 'Central 2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/almacenes/almacenes/alm-1/',
        expect.objectContaining({
          id_empresa: 'e1',
          nombre_almacen: 'Central 2',
          codigo_almacen: 'CEN',
          direccion: 'Av. Principal',
        }),
      ),
    );
  });

  it('eliminar un almacén llama al servicio', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/almacenes/almacenes/alm-1/'));
  });
});
