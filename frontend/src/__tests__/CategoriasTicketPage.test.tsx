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
import CategoriasTicketPage from '../pages/ServicioCliente/CategoriasTicketPage';

const categoriaApi = {
  id_categoria_ticket: 'cat-1',
  id_empresa: 'e1',
  nombre_categoria: 'Hardware',
  descripcion: 'Fallas de equipos',
  activo: true,
};

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/servicio-cliente/categorias-ticket')) return Promise.resolve([categoriaApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CategoriasTicketPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CategoriasTicketPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista las categorías', async () => {
    renderPage();
    expect(await screen.findByText('Hardware')).toBeInTheDocument();
    expect(screen.getByText('Fallas de equipos')).toBeInTheDocument();
  });

  it('valida el nombre requerido al crear', async () => {
    renderPage();
    await screen.findByText('Hardware');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva categoría' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique el nombre de la categoría/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una categoría enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_categoria_ticket: 'cat-2' });
    renderPage();
    await screen.findByText('Hardware');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva categoría' }));
    fireEvent.change(await screen.findByLabelText(/Nombre/), { target: { value: 'Software' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/servicio-cliente/categorias-ticket/',
        expect.objectContaining({
          id_empresa: 'e1',
          nombre_categoria: 'Software',
          activo: true,
        }),
      ),
    );
  });

  it('edita una categoría por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_categoria_ticket: 'cat-1' });
    renderPage();
    await screen.findByText('Hardware');
    const fila = screen.getByText('Hardware').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    const nombre = await screen.findByLabelText(/Nombre/);
    fireEvent.change(nombre, { target: { value: 'Hardware editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/servicio-cliente/categorias-ticket/cat-1/',
        expect.objectContaining({ nombre_categoria: 'Hardware editado' }),
      ),
    );
  });

  it('elimina una categoría con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Hardware');
    const fila = screen.getByText('Hardware').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/servicio-cliente/categorias-ticket/cat-1/'),
    );
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('Hardware');
    const fila = screen.getByText('Hardware').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('muestra error al fallar el guardado', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ error: 'duplicada' })));
    renderPage();
    await screen.findByText('Hardware');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva categoría' }));
    fireEvent.change(await screen.findByLabelText(/Nombre/), { target: { value: 'X' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/duplicada/)).toBeInTheDocument();
  });
});
