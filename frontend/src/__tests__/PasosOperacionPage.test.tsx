import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({ get: vi.fn(), post: vi.fn(), del: vi.fn() }));
vi.mock('../services/almacenesService', () => ({ almacenesService: { getAll: vi.fn() } }));

import { get, post, del } from '../services/api';
import { pasosOperacionService } from '../services/inventarioService';
import { almacenesService } from '../services/almacenesService';
import PasosOperacionPage from '../pages/Inventario/PasosOperacionPage';

describe('pasosOperacionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('list arma el querystring almacen+tipo', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await pasosOperacionService.list('alm-1', 'RECEPCION');
    expect(get).toHaveBeenCalledWith('/inventario/pasos-operacion/?almacen=alm-1&tipo_operacion=RECEPCION');
  });

  it('create postea el paso', async () => {
    vi.mocked(post).mockResolvedValue({ id_paso_operacion: 'p1' });
    await pasosOperacionService.create({
      id_empresa: 'e1', id_almacen: 'a1', tipo_operacion: 'ENTREGA', nombre_paso: 'Picking', secuencia: 1,
    });
    expect(post).toHaveBeenCalledWith('/inventario/pasos-operacion/', expect.objectContaining({ nombre_paso: 'Picking' }));
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    await pasosOperacionService.remove('p1');
    expect(del).toHaveBeenCalledWith('/inventario/pasos-operacion/p1/');
  });
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PasosOperacionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PasosOperacionPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(almacenesService.getAll).mockResolvedValue([
      { id_almacen: 'alm-1', nombre_almacen: 'Central', id_empresa: 'e1' },
    ]);
  });

  it('lista los pasos del almacén seleccionado y permite agregar uno', async () => {
    vi.mocked(get).mockResolvedValue([
      { id_paso_operacion: 'p1', id_empresa: 'e1', id_almacen: 'alm-1', tipo_operacion: 'RECEPCION', nombre_paso: 'Confirmación', secuencia: 1, activo: true },
    ]);
    vi.mocked(post).mockResolvedValue({ id_paso_operacion: 'p2' });

    renderPage();
    // Seleccionar almacén.
    fireEvent.mouseDown(await screen.findByLabelText('Almacén'));
    fireEvent.click(await screen.findByText('Central'));

    expect(await screen.findByText('Confirmación')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Nuevo paso'), { target: { value: 'Calidad' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/inventario/pasos-operacion/',
        expect.objectContaining({ nombre_paso: 'Calidad', secuencia: 2, tipo_operacion: 'RECEPCION' }),
      ),
    );
  });
});
