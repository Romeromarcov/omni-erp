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
import BaseConocimientoPage from '../pages/ServicioCliente/BaseConocimientoPage';

const articuloApi = {
  id_articulo: 'a1',
  id_empresa: 'e1',
  titulo: 'Cómo reiniciar el equipo',
  contenido: 'Mantén el botón 10 segundos',
  id_categoria_ticket: 'cat-1',
  palabras_clave: 'reinicio',
  visibilidad: 'PUBLICA',
  activo: true,
};

const categoriaApi = {
  id_categoria_ticket: 'cat-1',
  id_empresa: 'e1',
  nombre_categoria: 'Hardware',
  activo: true,
};

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/servicio-cliente/categorias-ticket/activas'))
      return Promise.resolve([categoriaApi]);
    if (url.startsWith('/servicio-cliente/articulos-conocimiento'))
      return Promise.resolve([articuloApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <BaseConocimientoPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('BaseConocimientoPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista los artículos con visibilidad y categoría', async () => {
    renderPage();
    expect(await screen.findByText('Cómo reiniciar el equipo')).toBeInTheDocument();
    expect(screen.getByText('Pública')).toBeInTheDocument();
    expect(screen.getAllByText('Hardware').length).toBeGreaterThan(0);
  });

  it('filtra por visibilidad y arma el querystring', async () => {
    renderPage();
    await screen.findByText('Cómo reiniciar el equipo');
    fireEvent.mouseDown(screen.getByLabelText('Visibilidad'));
    fireEvent.click(await screen.findByRole('option', { name: 'Interna' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        '/servicio-cliente/articulos-conocimiento/?id_empresa=e1&visibilidad=INTERNA',
      ),
    );
  });

  it('valida título y contenido requeridos', async () => {
    renderPage();
    await screen.findByText('Cómo reiniciar el equipo');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo artículo' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique el título y el contenido/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un artículo enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_articulo: 'a2' });
    renderPage();
    await screen.findByText('Cómo reiniciar el equipo');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo artículo' }));
    fireEvent.change(await screen.findByLabelText(/Título/), {
      target: { value: 'Guía de red' },
    });
    fireEvent.change(screen.getByLabelText(/Contenido/), {
      target: { value: 'Conecta el cable' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/servicio-cliente/articulos-conocimiento/',
        expect.objectContaining({
          id_empresa: 'e1',
          titulo: 'Guía de red',
          contenido: 'Conecta el cable',
          visibilidad: 'INTERNA',
          activo: true,
        }),
      ),
    );
  });

  it('edita un artículo por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_articulo: 'a1' });
    renderPage();
    await screen.findByText('Cómo reiniciar el equipo');
    const fila = screen.getByText('Cómo reiniciar el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    const titulo = await screen.findByLabelText(/Título/);
    fireEvent.change(titulo, { target: { value: 'Título editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/servicio-cliente/articulos-conocimiento/a1/',
        expect.objectContaining({ titulo: 'Título editado' }),
      ),
    );
  });

  it('elimina un artículo con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Cómo reiniciar el equipo');
    const fila = screen.getByText('Cómo reiniciar el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/servicio-cliente/articulos-conocimiento/a1/'),
    );
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('Cómo reiniciar el equipo');
    const fila = screen.getByText('Cómo reiniciar el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
