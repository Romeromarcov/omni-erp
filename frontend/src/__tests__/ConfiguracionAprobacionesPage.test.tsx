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
import ConfiguracionAprobacionesPage from '../pages/Aprobaciones/ConfiguracionAprobacionesPage';

const tipoApi = {
  id_tipo_aprobacion: 't1',
  id_empresa: 'e1',
  codigo_tipo: 'COMPRA',
  nombre_tipo: 'Aprobación de compra',
  descripcion: 'desc',
  modulo_origen: 'compras',
  activo: true,
};

const flujoApi = {
  id_flujo_aprobacion: 'f1',
  id_tipo_aprobacion: 't1',
  orden_etapa: 1,
  nombre_etapa: 'Jefatura',
  rol_aprobador: 'r1',
  id_usuario_aprobador: 'u1',
  monto_minimo: '0.00',
  monto_maximo: '1000.00',
  activo: true,
};

const usuarioApi = { id: 'u1', username: 'jefe', email: '', first_name: '', last_name: '', is_active: true, es_superusuario_omni: false };
const rolApi = { id_rol: 'r1', nombre_rol: 'Gerente', descripcion: '', activo: true };

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/gestion-aprobaciones/tipos-aprobacion')) return Promise.resolve([tipoApi]);
    if (url.startsWith('/gestion-aprobaciones/flujos-aprobacion')) return Promise.resolve([flujoApi]);
    if (url.startsWith('/core/usuarios')) return Promise.resolve([usuarioApi]);
    if (url.startsWith('/core/roles')) return Promise.resolve([rolApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ConfiguracionAprobacionesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ConfiguracionAprobacionesPage — Tipos', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista los tipos de aprobación', async () => {
    renderPage();
    expect(await screen.findByText('Aprobación de compra')).toBeInTheDocument();
    expect(screen.getByText('COMPRA')).toBeInTheDocument();
    expect(screen.getByText('compras')).toBeInTheDocument();
  });

  it('valida campos requeridos al crear un tipo', async () => {
    renderPage();
    await screen.findByText('Aprobación de compra');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo tipo' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete código, nombre y módulo/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un tipo enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_tipo_aprobacion: 't2' });
    renderPage();
    await screen.findByText('Aprobación de compra');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo tipo' }));
    fireEvent.change(await screen.findByLabelText(/Código/), { target: { value: 'GASTO' } });
    fireEvent.change(screen.getByLabelText(/Nombre/), { target: { value: 'Aprobación gasto' } });
    fireEvent.change(screen.getByLabelText(/Módulo de origen/), { target: { value: 'gastos' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/gestion-aprobaciones/tipos-aprobacion/',
        expect.objectContaining({
          id_empresa: 'e1',
          codigo_tipo: 'GASTO',
          nombre_tipo: 'Aprobación gasto',
          modulo_origen: 'gastos',
          activo: true,
        }),
      ),
    );
  });

  it('edita un tipo enviando el payload por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_tipo_aprobacion: 't1' });
    renderPage();
    await screen.findByText('Aprobación de compra');
    const fila = screen.getByText('Aprobación de compra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    const nombre = await screen.findByLabelText(/Nombre/);
    fireEvent.change(nombre, { target: { value: 'Nombre editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/gestion-aprobaciones/tipos-aprobacion/t1/',
        expect.objectContaining({ nombre_tipo: 'Nombre editado' }),
      ),
    );
  });

  it('elimina un tipo con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Aprobación de compra');
    const fila = screen.getByText('Aprobación de compra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/gestion-aprobaciones/tipos-aprobacion/t1/'),
    );
    confirmSpy.mockRestore();
  });

  it('no elimina un tipo si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('Aprobación de compra');
    const fila = screen.getByText('Aprobación de compra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('muestra error al fallar la creación del tipo', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ codigo_tipo: ['duplicado'] })));
    renderPage();
    await screen.findByText('Aprobación de compra');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo tipo' }));
    fireEvent.change(await screen.findByLabelText(/Código/), { target: { value: 'COMPRA' } });
    fireEvent.change(screen.getByLabelText(/Nombre/), { target: { value: 'x' } });
    fireEvent.change(screen.getByLabelText(/Módulo de origen/), { target: { value: 'compras' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/duplicado/)).toBeInTheDocument();
  });
});

describe('ConfiguracionAprobacionesPage — Flujos', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  async function irAFlujos() {
    renderPage();
    await screen.findByText('Aprobación de compra');
    fireEvent.click(screen.getByRole('tab', { name: 'Flujos (etapas)' }));
    await screen.findByText('Jefatura');
  }

  it('lista las etapas con tipo, rol y usuario resueltos', async () => {
    await irAFlujos();
    expect(screen.getByText('Jefatura')).toBeInTheDocument();
    expect(screen.getAllByText('Aprobación de compra').length).toBeGreaterThan(0);
    expect(screen.getByText('Gerente')).toBeInTheDocument();
    expect(screen.getByText('jefe')).toBeInTheDocument();
  });

  it('filtra etapas por tipo y arma el querystring', async () => {
    await irAFlujos();
    fireEvent.mouseDown(screen.getByLabelText('Tipo de aprobación'));
    fireEvent.click(await screen.findByRole('option', { name: 'Aprobación de compra' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        '/gestion-aprobaciones/flujos-aprobacion/?id_tipo_aprobacion=t1',
      ),
    );
  });

  it('valida tipo requerido al crear una etapa', async () => {
    await irAFlujos();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva etapa' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Seleccione el tipo de aprobación/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('valida nombre de etapa requerido', async () => {
    await irAFlujos();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva etapa' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Tipo de aprobación/));
    fireEvent.click(await screen.findByRole('option', { name: 'Aprobación de compra' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique el nombre de la etapa/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('valida orden de etapa inválido', async () => {
    await irAFlujos();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva etapa' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Tipo de aprobación/));
    fireEvent.click(await screen.findByRole('option', { name: 'Aprobación de compra' }));
    fireEvent.change(within(dialog).getByLabelText(/Nombre de la etapa/), {
      target: { value: 'Etapa X' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Orden de etapa/), { target: { value: '-5' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/orden de etapa debe ser un número/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una etapa enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_flujo_aprobacion: 'f2' });
    await irAFlujos();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva etapa' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Tipo de aprobación/));
    fireEvent.click(await screen.findByRole('option', { name: 'Aprobación de compra' }));
    fireEvent.change(within(dialog).getByLabelText(/Nombre de la etapa/), {
      target: { value: 'Dirección' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/gestion-aprobaciones/flujos-aprobacion/',
        expect.objectContaining({
          id_tipo_aprobacion: 't1',
          nombre_etapa: 'Dirección',
          orden_etapa: 1,
          rol_aprobador: null,
          id_usuario_aprobador: null,
          monto_minimo: null,
          monto_maximo: null,
        }),
      ),
    );
  });

  it('edita una etapa enviando el payload por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_flujo_aprobacion: 'f1' });
    await irAFlujos();
    const fila = screen.getByText('Jefatura').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    const nombre = await screen.findByLabelText(/Nombre de la etapa/);
    fireEvent.change(nombre, { target: { value: 'Jefatura editada' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/gestion-aprobaciones/flujos-aprobacion/f1/',
        expect.objectContaining({
          nombre_etapa: 'Jefatura editada',
          rol_aprobador: 'r1',
          id_usuario_aprobador: 'u1',
          monto_minimo: '0.00',
          monto_maximo: '1000.00',
        }),
      ),
    );
  });

  it('elimina una etapa con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    await irAFlujos();
    const fila = screen.getByText('Jefatura').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/gestion-aprobaciones/flujos-aprobacion/f1/'),
    );
    confirmSpy.mockRestore();
  });
});
