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
import CategoriasGastoPage from '../pages/Gastos/CategoriasGastoPage';

const categoriaApi = {
  id_categoria_gasto: 'cat-1',
  id_empresa: 'e1',
  nombre_categoria: 'Servicios',
  descripcion: 'Gastos de servicios',
  id_cuenta_contable: 'cta-1',
  requiere_factura: true,
  activo: true,
};

const cuentaApi = {
  id_cuenta_contable: 'cta-1',
  codigo_cuenta: '6.1.01',
  nombre_cuenta: 'Servicios básicos',
};

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/contabilidad/plan-cuentas')) return Promise.resolve([cuentaApi]);
    if (url.startsWith('/gastos/categorias-gasto')) return Promise.resolve([categoriaApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CategoriasGastoPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CategoriasGastoPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista las categorías con su cuenta contable', async () => {
    renderPage();
    expect(await screen.findByText('Servicios')).toBeInTheDocument();
    expect(screen.getByText('6.1.01 — Servicios básicos')).toBeInTheDocument();
  });

  it('valida el nombre requerido al crear', async () => {
    renderPage();
    await screen.findByText('Servicios');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva categoría' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique el nombre de la categoría/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una categoría con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValue({ id_categoria_gasto: 'cat-2' });
    renderPage();
    await screen.findByText('Servicios');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva categoría' }));
    fireEvent.change(await screen.findByLabelText(/Nombre/), {
      target: { value: 'Viáticos' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/gastos/categorias-gasto/',
        expect.objectContaining({
          id_empresa: 'e1',
          nombre_categoria: 'Viáticos',
          descripcion: null,
          id_cuenta_contable: null,
          requiere_factura: false,
          activo: true,
        }),
      ),
    );
  });

  it('edita una categoría enviando el payload por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_categoria_gasto: 'cat-1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const nombre = await screen.findByLabelText(/Nombre/);
    fireEvent.change(nombre, { target: { value: 'Servicios editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/gastos/categorias-gasto/cat-1/',
        expect.objectContaining({
          nombre_categoria: 'Servicios editado',
          id_cuenta_contable: 'cta-1',
          requiere_factura: true,
        }),
      ),
    );
  });

  it('elimina con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/gastos/categorias-gasto/cat-1/'));
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('muestra error al fallar el guardado (mensajeDeError)', async () => {
    vi.mocked(post).mockRejectedValue(
      new Error(JSON.stringify({ nombre_categoria: ['Ya existe.'] })),
    );
    renderPage();
    await screen.findByText('Servicios');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva categoría' }));
    fireEvent.change(await screen.findByLabelText(/Nombre/), { target: { value: 'X' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Ya existe/)).toBeInTheDocument();
  });
});
