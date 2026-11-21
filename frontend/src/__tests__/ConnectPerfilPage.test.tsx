import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const authState = {
  token: null as string | null,
  isLoading: true,
  user: null,
};

vi.mock('../services/api', () => ({
  API_URL: '/api',
  get: vi.fn(),
  patch: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'emp-1' }));
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => authState,
}));

import { get, patch } from '../services/api';
import ConnectPerfilPage from '../pages/Connect/ConnectPerfilPage';
import { buildNavigation } from '../config/navigation';
import { connectRoutes } from '../routes/connectRoutes';
import { Routes } from 'react-router-dom';
import AppRouter from '../router';

const miPerfilFixture = {
  id_perfil: 'perf-1',
  id_empresa: 'emp-1',
  usuario: 'usr-1',
  slug: 'ana-gomez',
  nombre_publico: 'Ana Gómez',
  cargo: 'Gerente de Ventas',
  bio: 'Especialista en soluciones B2B.',
  telefono_publico: '+584121112233',
  email_publico: 'ana@omni.com',
  tema: 'CORPORATIVO',
  botones: [{ tipo: 'web', etiqueta: 'Web', valor: 'https://omni.com' }],
  plantilla_bloqueada: false,
  activo: true,
  fecha_creacion: '2026-11-20T10:00:00Z',
  fecha_actualizacion: '2026-11-20T10:00:00Z',
};

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ConnectPerfilPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ConnectPerfilPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    window.history.pushState({}, '', '/');
  });

  it('carga el perfil existente, permite editar campos/botones, copiar enlace y guardar', async () => {
    vi.mocked(get).mockResolvedValueOnce(miPerfilFixture);
    vi.mocked(patch).mockResolvedValueOnce({
      ...miPerfilFixture,
      nombre_publico: 'Ana Gómez Actualizada',
      botones: [
        { tipo: 'web', etiqueta: 'Web', valor: 'https://omni.com' },
        { tipo: 'whatsapp', etiqueta: 'Escríbeme', valor: '+584121112233' },
      ],
    });

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextMock },
      configurable: true,
    });

    renderEditor();

    expect(await screen.findByDisplayValue('Ana Gómez')).toBeInTheDocument();
    expect(screen.getByDisplayValue('ana-gomez')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/connect/perfiles/mi-perfil/?empresa_id=emp-1');

    fireEvent.click(screen.getByRole('button', { name: /copiar enlace/i }));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith(expect.stringContaining('/c/ana-gomez'));
    });

    fireEvent.change(screen.getByLabelText(/^nombre público/i), {
      target: { value: 'Ana Gómez Actualizada' },
    });

    fireEvent.click(screen.getByRole('button', { name: /agregar botón/i }));
    const etiquetaInputs = screen.getAllByLabelText(/^etiqueta/i);
    const valorInputs = screen.getAllByLabelText(/^valor \/ url/i);
    fireEvent.change(etiquetaInputs.at(-1)!, { target: { value: 'Escríbeme' } });
    fireEvent.change(valorInputs.at(-1)!, { target: { value: '+584121112233' } });

    fireEvent.click(screen.getByRole('button', { name: /guardar perfil/i }));

    expect(await screen.findByText('Perfil guardado correctamente.')).toBeInTheDocument();
    expect(patch).toHaveBeenCalledWith(
      '/connect/perfiles/mi-perfil/?empresa_id=emp-1',
      expect.objectContaining({
        slug: 'ana-gomez',
        nombre_publico: 'Ana Gómez Actualizada',
      }),
    );
  });

  it('muestra aviso inicial si no tiene perfil (404) y deshabilita tema cuando plantilla_bloqueada es true', async () => {
    const err404 = Object.assign(new Error('No existe'), { status: 404 });
    vi.mocked(get).mockRejectedValueOnce(err404);

    renderEditor();

    expect(
      await screen.findByText(/aún no has creado tu tarjeta digital en esta empresa/i),
    ).toBeInTheDocument();

    vi.mocked(get).mockResolvedValueOnce({
      ...miPerfilFixture,
      plantilla_bloqueada: true,
    });
    renderEditor();

    expect(
      await screen.findByText(/la plantilla visual está bloqueada por el administrador/i),
    ).toBeInTheDocument();
  });

  it('el enrutador público /c/:slug renderiza sin bloquearse aunque isLoading sea true', async () => {
    authState.token = null;
    authState.isLoading = true;
    window.history.pushState({}, '', '/c/ana-gomez');

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          slug: 'ana-gomez',
          nombre_publico: 'Ana Gómez',
          cargo: 'Gerente',
          bio: '',
          telefono_publico: '',
          email_publico: '',
          tema: 'CLASICO',
          botones: [],
          empresa_nombre: 'OMNI',
          acepta_leads: true,
          consentimiento_texto: 'Acepto',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    render(<AppRouter />);

    expect(await screen.findByRole('heading', { name: 'Ana Gómez' })).toBeInTheDocument();
    expect(screen.queryByText(/iniciar sesión/i)).not.toBeInTheDocument();
  });

  it('expone Omni Connect en navigation y maneja error de carga inicial 500', async () => {
    const sections = buildNavigation('emp-1', { esSuperusuarioOmni: false });
    const connectSec = sections.find((s) => s.id === 'connect');
    expect(connectSec?.items?.[0]?.path).toBe('/connect/perfil');

    vi.mocked(get).mockRejectedValueOnce(Object.assign(new Error('Fallo de red'), { status: 500 }));
    renderEditor();
    expect(await screen.findByText('Fallo de red')).toBeInTheDocument();
  });

  it('cubre connectRoutes, edición completa, eliminación de botón, validaciones y error de guardado', async () => {
    vi.mocked(get).mockResolvedValueOnce(miPerfilFixture);
    vi.mocked(patch).mockRejectedValueOnce(new Error('Slug ya en uso'));

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/connect/perfil']}>
          <Routes>{connectRoutes()}</Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByDisplayValue('Ana Gómez')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/^cargo/i), { target: { value: 'Directora' } });
    fireEvent.change(screen.getByLabelText(/^teléfono público/i), {
      target: { value: '+584149998877' },
    });
    fireEvent.change(screen.getByLabelText(/^correo público/i), {
      target: { value: 'dir@omni.com' },
    });
    fireEvent.change(screen.getByLabelText(/^biografía/i), {
      target: { value: 'Nueva bio' },
    });

    fireEvent.click(screen.getByRole('button', { name: /eliminar botón 1/i }));
    fireEvent.click(screen.getByRole('button', { name: /guardar perfil/i }));
    expect(await screen.findByText('Slug ya en uso')).toBeInTheDocument();

    // Limpiar slug dispara validación cliente antes de llamar PATCH
    fireEvent.change(screen.getByLabelText(/^slug público/i), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /guardar perfil/i }));
    expect(
      await screen.findByText(/el slug público y el nombre público son obligatorios/i),
    ).toBeInTheDocument();
  });
});
