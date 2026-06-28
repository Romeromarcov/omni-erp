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
import UbicacionesAlmacenPage from '../pages/Inventario/UbicacionesAlmacenPage';

const ubicacionApi = {
  id_ubicacion: 'u1',
  id_empresa: 'e1',
  id_almacen: 'alm-1',
  codigo_ubicacion: 'A-01',
  nombre_ubicacion: 'Estante A',
  tipo_ubicacion: 'ESTANTERIA',
  pasillo: '1',
  estante: 'A',
  nivel: null,
  posicion: null,
  capacidad_maxima: null,
  unidad_capacidad: null,
  temperatura_minima: null,
  temperatura_maxima: null,
  activo: true,
  requiere_autorizacion: false,
  observaciones: null,
};

const almacenApi = {
  id_almacen: 'alm-1',
  nombre_almacen: 'Central',
  codigo_almacen: 'CEN',
  direccion: null,
  activo: true,
  id_empresa: 'e1',
};

function mockApi() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/almacenes/almacenes/')) return Promise.resolve([almacenApi]);
    if (url.startsWith('/almacenes/ubicaciones-almacen/')) return Promise.resolve([ubicacionApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <UbicacionesAlmacenPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('UbicacionesAlmacenPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
  });

  it('lista las ubicaciones con el nombre del almacén', async () => {
    renderPage();
    expect(await screen.findByText('Estante A')).toBeInTheDocument();
    expect(screen.getByText('Central')).toBeInTheDocument();
  });

  it('valida campos requeridos al crear', async () => {
    renderPage();
    await screen.findByText('Estante A');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva ubicación' }));
    expect(await screen.findByText('Nueva ubicación', { selector: 'h2' })).toBeInTheDocument();
    // El select de almacén del filtro arrancó vacío → el form también, así que falla validación.
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete almacén, código y nombre/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una ubicación con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_ubicacion: 'u2' });
    renderPage();
    await screen.findByText('Estante A');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva ubicación' }));
    await screen.findByText('Nueva ubicación', { selector: 'h2' });
    const dialog = within(screen.getByRole('dialog'));

    fireEvent.mouseDown(dialog.getByLabelText(/Almacén/));
    fireEvent.click(await screen.findByRole('option', { name: 'Central' }));

    fireEvent.change(dialog.getByLabelText(/Código/), { target: { value: 'B-02' } });
    fireEvent.change(dialog.getByLabelText(/Nombre/), { target: { value: 'Estante B' } });
    fireEvent.click(dialog.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/almacenes/ubicaciones-almacen/',
        expect.objectContaining({
          id_almacen: 'alm-1',
          codigo_ubicacion: 'B-02',
          nombre_ubicacion: 'Estante B',
          tipo_ubicacion: 'ESTANTERIA',
          activo: true,
        }),
      ),
    );
  });
});
