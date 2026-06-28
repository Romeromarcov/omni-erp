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
import PersonalizacionPage from '../pages/Personalizacion/PersonalizacionPage';

const activaApi = {
  id_config: 'c2',
  id_empresa: 'e1',
  version: 2,
  descripcion: 'Versión vigente',
  config_yaml: 'entidades:\n  - Equipo',
  config_dict: { entidades: ['Equipo'] },
  activo: true,
  fecha_creacion: '2026-06-20T10:00:00Z',
};

const historialApi = [
  activaApi,
  {
    id_config: 'c1',
    id_empresa: 'e1',
    version: 1,
    descripcion: 'Versión inicial',
    config_yaml: 'entidades: []',
    config_dict: {},
    activo: false,
    fecha_creacion: '2026-06-10T10:00:00Z',
  },
];

/** Por defecto: hay config activa + historial con dos versiones. */
function setupGet(opts?: { sinActiva?: boolean }) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.includes('/configuraciones/activa/')) {
      if (opts?.sinActiva) {
        const e = new Error('{"error":"No hay configuración activa"}') as Error & {
          status?: number;
        };
        e.status = 404;
        return Promise.reject(e);
      }
      return Promise.resolve(activaApi);
    }
    if (url.includes('/configuraciones/historial/')) return Promise.resolve(historialApi);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PersonalizacionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PersonalizacionPage — configuración activa', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('renderiza el encabezado', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { name: 'Personalización' }),
    ).toBeInTheDocument();
  });

  it('muestra la configuración activa cuando existe', async () => {
    renderPage();
    expect(await screen.findByText('Versión 2')).toBeInTheDocument();
    // "Versión vigente" aparece en el panel activo y en su fila del historial.
    expect(screen.getAllByText('Versión vigente').length).toBeGreaterThanOrEqual(1);
  });

  it('muestra un mensaje claro cuando NO hay configuración activa', async () => {
    setupGet({ sinActiva: true });
    renderPage();
    expect(
      await screen.findByText(/No hay ninguna configuración activa/),
    ).toBeInTheDocument();
  });
});

describe('PersonalizacionPage — historial', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista las versiones del historial', async () => {
    renderPage();
    expect(await screen.findByText('v1')).toBeInTheDocument();
    expect(screen.getByText('v2')).toBeInTheDocument();
    expect(screen.getByText('Versión inicial')).toBeInTheDocument();
  });

  it('muestra el estado vacío cuando no hay versiones', async () => {
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.includes('/configuraciones/activa/')) {
        const e = new Error('404') as Error & { status?: number };
        e.status = 404;
        return Promise.reject(e);
      }
      return Promise.resolve([]);
    });
    renderPage();
    expect(
      await screen.findByText(/Sin versiones de configuración/),
    ).toBeInTheDocument();
  });

  it('solo la versión no activa muestra el botón Activar', async () => {
    renderPage();
    await screen.findByText('v1');
    // Una sola versión inactiva (v1) → un solo botón Activar.
    expect(screen.getAllByRole('button', { name: 'Activar' })).toHaveLength(1);
  });
});

describe('PersonalizacionPage — activar (rollback)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('activa una versión con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ id_config: 'c1', activo: true });
    renderPage();
    await screen.findByText('v1');
    fireEvent.click(screen.getByRole('button', { name: 'Activar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/personalizacion/configuraciones/c1/activar/', {}),
    );
    confirmSpy.mockRestore();
  });

  it('no activa si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('v1');
    fireEvent.click(screen.getByRole('button', { name: 'Activar' }));
    expect(post).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('muestra el error del backend al fallar la activación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockRejectedValue(new Error('boom'));
    renderPage();
    await screen.findByText('v1');
    fireEvent.click(screen.getByRole('button', { name: 'Activar' }));
    expect(await screen.findByText(/boom/)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });
});

describe('PersonalizacionPage — crear versión', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('crea una versión con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValue({ id_config: 'c3' });
    renderPage();
    await screen.findByText('v1');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva versión' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Descripción/), {
      target: { value: 'v3 nueva' },
    });
    fireEvent.change(within(dialog).getByLabelText(/config_yaml/), {
      target: { value: 'entidades:\n  - Contrato' },
    });
    fireEvent.change(within(dialog).getByLabelText(/config_dict/), {
      target: { value: '{"entidades":["Contrato"]}' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/personalizacion/configuraciones/',
        expect.objectContaining({
          id_empresa: 'e1',
          descripcion: 'v3 nueva',
          config_yaml: 'entidades:\n  - Contrato',
          config_dict: { entidades: ['Contrato'] },
        }),
      ),
    );
  });

  it('valida que el config_dict sea JSON válido', async () => {
    renderPage();
    await screen.findByText('v1');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva versión' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/config_dict/), {
      target: { value: '{ no es json' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/config_dict \(JSON\) no es válido/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('muestra el error del backend sin cerrar el diálogo', async () => {
    vi.mocked(post).mockRejectedValue(new Error('boom-crear'));
    renderPage();
    await screen.findByText('v1');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva versión' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Descripción/), {
      target: { value: 'falla' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/boom-crear/)).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('PersonalizacionPage — detalle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('abre el detalle de una versión con yaml y json', async () => {
    renderPage();
    await screen.findByText('v1');
    const botonesDetalle = screen.getAllByRole('button', { name: 'Ver detalle' });
    fireEvent.click(botonesDetalle[botonesDetalle.length - 1]); // v1 (última fila)
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Versión 1')).toBeInTheDocument();
    expect(within(dialog).getByText('config_yaml')).toBeInTheDocument();
    expect(within(dialog).getByText('config_dict')).toBeInTheDocument();
  });
});
