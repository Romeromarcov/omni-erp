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
import MigracionDatosPage from '../pages/MigracionDatos/MigracionDatosPage';

const plantillaApi = {
  id_plantilla_migracion: 'pl1',
  nombre_plantilla: 'Clientes CSV',
  modulo_destino: 'crm',
  modelo_destino: 'Cliente',
  formato_archivo: 'CSV',
  estructura_json: { columnas: ['nombre', 'rif'] },
  activo: true,
};

const procesoApi = {
  id_proceso_migracion: 'pr1',
  id_empresa: 'e1',
  id_plantilla_migracion: 'pl1',
  id_usuario_ejecutor: 'u1',
  fecha_inicio: '2026-06-24T00:00:00Z',
  fecha_fin: null,
  estado_proceso: 'COMPLETADO',
  total_registros_procesados: 10,
  total_registros_exitosos: 9,
  total_registros_fallidos: 1,
  ruta_archivo_cargado: '/tmp/clientes.csv',
  ruta_archivo_errores: null,
};

const errorApi = {
  id_detalle_error: 'd1',
  id_proceso_migracion: 'pr1',
  numero_fila_archivo: 3,
  campo_error: 'rif',
  mensaje_error: 'RIF inválido',
  datos_originales_json: { rif: 'XXX' },
  fecha_registro_error: '2026-06-24T00:00:00Z',
};

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/migracion-datos/plantillas-migracion'))
      return Promise.resolve([plantillaApi]);
    if (url.startsWith('/migracion-datos/procesos-migracion'))
      return Promise.resolve([procesoApi]);
    if (url.startsWith('/migracion-datos/detalles-error-migracion'))
      return Promise.resolve([errorApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MigracionDatosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const irAProcesos = () => fireEvent.click(screen.getByRole('tab', { name: 'Procesos' }));
const irAErrores = () => fireEvent.click(screen.getByRole('tab', { name: 'Errores' }));

describe('MigracionDatosPage — tab Plantillas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('renderiza el encabezado y los tres tabs', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { name: 'Migración de Datos' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Plantillas' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Procesos' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Errores' })).toBeInTheDocument();
  });

  it('lista las plantillas', async () => {
    renderPage();
    expect(await screen.findByText('Clientes CSV')).toBeInTheDocument();
    expect(screen.getByText('crm')).toBeInTheDocument();
  });

  it('valida el nombre requerido al crear', async () => {
    renderPage();
    await screen.findByText('Clientes CSV');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva plantilla' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique el nombre de la plantilla/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('valida que la estructura JSON sea válida', async () => {
    renderPage();
    await screen.findByText('Clientes CSV');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva plantilla' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Nombre de la plantilla/), {
      target: { value: 'Productos' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Módulo destino/), {
      target: { value: 'inventario' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Modelo destino/), {
      target: { value: 'Producto' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Estructura JSON/), {
      target: { value: '{ no es json' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/La estructura JSON no es válida/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una plantilla con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValue({ id_plantilla_migracion: 'pl2' });
    renderPage();
    await screen.findByText('Clientes CSV');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva plantilla' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Nombre de la plantilla/), {
      target: { value: 'Productos XLSX' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Módulo destino/), {
      target: { value: 'inventario' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Modelo destino/), {
      target: { value: 'Producto' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Estructura JSON/), {
      target: { value: '{"columnas":["sku"]}' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/migracion-datos/plantillas-migracion/',
        expect.objectContaining({
          nombre_plantilla: 'Productos XLSX',
          modulo_destino: 'inventario',
          modelo_destino: 'Producto',
          estructura_json: { columnas: ['sku'] },
          activo: true,
        }),
      ),
    );
  });

  it('muestra el 403 del backend sin romper (no superusuario)', async () => {
    vi.mocked(post).mockRejectedValue(
      Object.assign(new Error(JSON.stringify({ detail: 'No tiene permisos para esta acción.' })), {
        status: 403,
      }),
    );
    renderPage();
    await screen.findByText('Clientes CSV');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva plantilla' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Nombre de la plantilla/), {
      target: { value: 'Sin permiso' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Módulo destino/), {
      target: { value: 'crm' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Modelo destino/), {
      target: { value: 'Cliente' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/No tiene permisos/)).toBeInTheDocument();
    // El diálogo sigue abierto (no se cerró por el error).
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('edita una plantilla por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_plantilla_migracion: 'pl1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Nombre de la plantilla/), {
      target: { value: 'Clientes CSV v2' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/migracion-datos/plantillas-migracion/pl1/',
        expect.objectContaining({ nombre_plantilla: 'Clientes CSV v2' }),
      ),
    );
  });

  it('elimina con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/migracion-datos/plantillas-migracion/pl1/'),
    );
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});

describe('MigracionDatosPage — tab Procesos', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista los procesos con el chip de estado y resuelve la plantilla', async () => {
    renderPage();
    irAProcesos();
    expect(await screen.findByText('Completado')).toBeInTheDocument();
    // La plantilla se resuelve por nombre.
    expect(screen.getAllByText('Clientes CSV').length).toBeGreaterThan(0);
  });

  it('valida la plantilla requerida al crear', async () => {
    renderPage();
    irAProcesos();
    await screen.findByText('Completado');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo proceso' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Seleccione la plantilla/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un proceso con el payload whitelisted', async () => {
    vi.mocked(post).mockResolvedValue({ id_proceso_migracion: 'pr2' });
    renderPage();
    irAProcesos();
    await screen.findByText('Completado');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo proceso' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Plantilla/));
    fireEvent.click(await screen.findByRole('option', { name: 'Clientes CSV' }));
    fireEvent.change(within(dialog).getByLabelText(/Usuario ejecutor/), {
      target: { value: 'u9' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Ruta del archivo cargado/), {
      target: { value: '/tmp/x.csv' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/migracion-datos/procesos-migracion/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_plantilla_migracion: 'pl1',
          id_usuario_ejecutor: 'u9',
          estado_proceso: 'PENDIENTE',
          ruta_archivo_cargado: '/tmp/x.csv',
          ruta_archivo_errores: null,
        }),
      ),
    );
  });

  it('muestra error al fallar la creación', async () => {
    vi.mocked(post).mockRejectedValue(new Error('boom'));
    renderPage();
    irAProcesos();
    await screen.findByText('Completado');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo proceso' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Plantilla/));
    fireEvent.click(await screen.findByRole('option', { name: 'Clientes CSV' }));
    fireEvent.change(within(dialog).getByLabelText(/Usuario ejecutor/), {
      target: { value: 'u9' },
    });
    fireEvent.change(within(dialog).getByLabelText(/Ruta del archivo cargado/), {
      target: { value: '/tmp/x.csv' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/boom/)).toBeInTheDocument();
  });
});

describe('MigracionDatosPage — tab Errores', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('muestra el estado vacío hasta seleccionar un proceso', async () => {
    renderPage();
    irAErrores();
    expect(
      await screen.findByText(/Seleccione un proceso para ver sus errores/),
    ).toBeInTheDocument();
  });

  it('lista los errores al filtrar por proceso', async () => {
    renderPage();
    irAErrores();
    const combo = await screen.findByLabelText(/Proceso/);
    fireEvent.mouseDown(combo);
    // La opción muestra "<plantilla> — <estado>".
    fireEvent.click(await screen.findByRole('option', { name: /Clientes CSV — Completado/ }));
    expect(await screen.findByText('RIF inválido')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(
      '/migracion-datos/detalles-error-migracion/?id_proceso_migracion=pr1',
    );
  });
});
