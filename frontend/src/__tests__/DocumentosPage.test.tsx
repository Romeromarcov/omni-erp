import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  postForm: vi.fn(),
  fetcher: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));

import { get, post, del, postForm, fetcher } from '../services/api';
import DocumentosPage from '../pages/GestionDocumental/DocumentosPage';

const carpetaApi = {
  id_carpeta: 'c1',
  id_empresa: 'e1',
  nombre_carpeta: 'Facturas',
  id_carpeta_padre: null,
  es_publica: false,
  activo: true,
  id_usuario_creacion: 'u1',
};

const documentoApi = {
  id_documento: 'd1',
  id_empresa: 'e1',
  nombre_archivo: 'factura.pdf',
  tipo_contenido: 'application/pdf',
  tamano_bytes: 2048,
  ruta_almacenamiento: 's3/key',
  descripcion: 'Factura enero',
  activo: true,
  version: 1,
  id_carpeta: 'c1',
};

const vinculoApi = {
  id_vinculo: 'v1',
  id_documento: 'd1',
  id_entidad_origen: 'g1',
  nombre_modelo_origen: 'gastos.Gasto',
  tipo_vinculo: 'RESPALDO',
};

const permisoApi = {
  id_permiso_documento: 'pm1',
  id_documento: 'd1',
  id_usuario: 'u9',
  id_rol: null,
  puede_ver: true,
  puede_editar: false,
  puede_eliminar: false,
};

function setGet(opts: { carpetas?: unknown[]; documentos?: unknown[]; vinculos?: unknown[]; permisos?: unknown[] } = {}) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/gestion-documental/carpetas')) return Promise.resolve(opts.carpetas ?? [carpetaApi]);
    if (url.startsWith('/gestion-documental/documentos')) return Promise.resolve(opts.documentos ?? [documentoApi]);
    if (url.startsWith('/gestion-documental/vinculos-documento')) return Promise.resolve(opts.vinculos ?? []);
    if (url.startsWith('/gestion-documental/permisos-documento')) return Promise.resolve(opts.permisos ?? []);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DocumentosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  setGet();
});

describe('DocumentosPage — lista y navegación', () => {
  it('lista carpetas y documentos', async () => {
    renderPage();
    expect(await screen.findByText('factura.pdf')).toBeInTheDocument();
    expect(screen.getByText('Facturas')).toBeInTheDocument();
    expect(screen.getByText('Factura enero')).toBeInTheDocument();
  });

  it('navega por carpeta y filtra', async () => {
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Facturas' }));
    await waitFor(() => {
      const llamadas = vi.mocked(get).mock.calls.map((c) => c[0]);
      expect(llamadas.some((u) => u.includes('id_carpeta=c1'))).toBe(true);
    });
    fireEvent.click(screen.getByRole('button', { name: 'Todas' }));
  });

  it('busca por nombre', async () => {
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'fac' } });
    await waitFor(() => {
      const llamadas = vi.mocked(get).mock.calls.map((c) => c[0]);
      expect(llamadas.some((u) => u.includes('search=fac'))).toBe(true);
    });
  });
});

describe('DocumentosPage — carpetas CRUD', () => {
  it('crea una carpeta', async () => {
    vi.mocked(post).mockResolvedValueOnce(carpetaApi);
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: /Nueva carpeta/ }));
    fireEvent.change(await screen.findByLabelText(/Nombre de la carpeta/), {
      target: { value: 'Contratos' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/gestion-documental/carpetas/',
        expect.objectContaining({ nombre_carpeta: 'Contratos', id_empresa: 'e1' }),
      ),
    );
  });

  it('valida nombre vacío al crear carpeta', async () => {
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: /Nueva carpeta/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText('Indique el nombre de la carpeta.')).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('edita una carpeta', async () => {
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Editar carpeta Facturas' }));
    expect(await screen.findByText('Editar carpeta')).toBeInTheDocument();
  });

  it('elimina una carpeta tras confirmar', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValueOnce(undefined);
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar carpeta Facturas' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/gestion-documental/carpetas/c1/'),
    );
  });

  it('no elimina carpeta si se cancela la confirmación', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar carpeta Facturas' }));
    expect(del).not.toHaveBeenCalled();
  });
});

describe('DocumentosPage — subir documento', () => {
  it('sube un archivo con FormData', async () => {
    vi.mocked(postForm).mockResolvedValueOnce(documentoApi);
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: /Subir documento/ }));
    const archivo = new File(['x'], 'nuevo.pdf', { type: 'application/pdf' });
    const input = await screen.findByLabelText('Archivo');
    fireEvent.change(input, { target: { files: [archivo] } });
    fireEvent.change(screen.getByLabelText('Descripción'), { target: { value: 'Doc nuevo' } });
    const dialogos = screen.getAllByRole('button', { name: 'Subir' });
    fireEvent.click(dialogos[dialogos.length - 1]);
    await waitFor(() => expect(postForm).toHaveBeenCalledTimes(1));
    const fd = vi.mocked(postForm).mock.calls[0][1] as FormData;
    expect((fd.get('archivo') as File).name).toBe('nuevo.pdf');
    expect(fd.get('descripcion')).toBe('Doc nuevo');
  });

  it('valida que falta archivo al subir', async () => {
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: /Subir documento/ }));
    const botones = await screen.findAllByRole('button', { name: 'Subir' });
    fireEvent.click(botones[botones.length - 1]);
    expect(await screen.findByText('Seleccione un archivo.')).toBeInTheDocument();
    expect(postForm).not.toHaveBeenCalled();
  });

  it('maneja el error de subida sin archivo seleccionado (input vacío)', async () => {
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: /Subir documento/ }));
    const input = await screen.findByLabelText('Archivo');
    fireEvent.change(input, { target: { files: [] } });
    expect(input).toBeInTheDocument();
  });
});

describe('DocumentosPage — descargar / eliminar documento', () => {
  it('descarga un documento', async () => {
    vi.mocked(fetcher).mockResolvedValueOnce({
      url: 'https://s3/firmada',
      expires_in: 3600,
      nombre_archivo: 'factura.pdf',
    });
    renderPage();
    await screen.findByText('factura.pdf');
    // Espiar createElement DESPUÉS del render para no interceptar el portal de MUI.
    const anchor = { href: '', download: '', rel: '', click: vi.fn() } as unknown as HTMLAnchorElement;
    const realCreate = document.createElement.bind(document);
    const createEl = vi
      .spyOn(document, 'createElement')
      .mockImplementation((tag: string) =>
        tag === 'a' ? anchor : (realCreate(tag) as HTMLElement),
      );
    const append = vi.spyOn(document.body, 'appendChild').mockImplementation((n) => n);
    const remove = vi.spyOn(document.body, 'removeChild').mockImplementation((n) => n);
    fireEvent.click(screen.getByRole('button', { name: 'Descargar' }));
    await waitFor(() =>
      expect(fetcher).toHaveBeenCalledWith('/gestion-documental/documentos/d1/descargar/'),
    );
    await waitFor(() => expect(anchor.download).toBe('factura.pdf'));
    createEl.mockRestore();
    append.mockRestore();
    remove.mockRestore();
  });

  it('muestra error si la descarga falla', async () => {
    vi.mocked(fetcher).mockRejectedValueOnce(new Error());
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Descargar' }));
    expect(await screen.findByText('No se pudo descargar el documento.')).toBeInTheDocument();
  });

  it('elimina un documento tras confirmar', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValueOnce(undefined);
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/gestion-documental/documentos/d1/eliminar-archivo/'),
    );
  });

  it('no elimina documento si se cancela', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
  });
});

describe('DocumentosPage — vínculos y permisos (drawer)', () => {
  it('abre el drawer y crea un vínculo', async () => {
    vi.mocked(post).mockResolvedValueOnce(vinculoApi);
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Vínculos / Permisos' }));
    expect(await screen.findByText('Vínculos')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Modelo de origen'), {
      target: { value: 'gastos.Gasto' },
    });
    fireEvent.change(screen.getByLabelText('ID de la entidad'), { target: { value: 'g1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar vínculo' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/gestion-documental/vinculos-documento/',
        expect.objectContaining({ id_documento: 'd1', nombre_modelo_origen: 'gastos.Gasto' }),
      ),
    );
  });

  it('valida vínculo incompleto', async () => {
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Vínculos / Permisos' }));
    await screen.findByText('Vínculos');
    fireEvent.click(screen.getByRole('button', { name: 'Agregar vínculo' }));
    expect(await screen.findByText('Complete la entidad y el modelo de origen.')).toBeInTheDocument();
  });

  it('lista, edita y elimina un vínculo existente', async () => {
    setGet({ vinculos: [vinculoApi] });
    vi.mocked(del).mockResolvedValueOnce(undefined);
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Vínculos / Permisos' }));
    expect(await screen.findByText(/gastos\.Gasto/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Editar' })[0]);
    expect(screen.getByRole('button', { name: 'Actualizar vínculo' })).toBeInTheDocument();
    // Cancelar edición
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Eliminar' })[0]);
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/gestion-documental/vinculos-documento/v1/'),
    );
  });

  it('crea un permiso', async () => {
    vi.mocked(post).mockResolvedValueOnce(permisoApi);
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Vínculos / Permisos' }));
    expect(await screen.findByText('Permisos')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('ID Usuario'), { target: { value: 'u9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar permiso' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/gestion-documental/permisos-documento/',
        expect.objectContaining({ id_documento: 'd1', id_usuario: 'u9' }),
      ),
    );
  });

  it('valida permiso sin usuario ni rol', async () => {
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Vínculos / Permisos' }));
    await screen.findByText('Permisos');
    fireEvent.click(screen.getByRole('button', { name: 'Agregar permiso' }));
    expect(await screen.findByText('Indique un usuario o un rol.')).toBeInTheDocument();
  });

  it('lista, edita y elimina un permiso existente', async () => {
    setGet({ permisos: [permisoApi] });
    vi.mocked(del).mockResolvedValueOnce(undefined);
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Vínculos / Permisos' }));
    expect(await screen.findByText(/Usuario u9/)).toBeInTheDocument();
    // Vínculos está vacío en este caso, así que el único "Editar" es el del permiso.
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    expect(screen.getByRole('button', { name: 'Actualizar permiso' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    // El botón Eliminar del permiso es el último de la lista del drawer.
    const eliminarBtns = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(eliminarBtns[eliminarBtns.length - 1]);
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/gestion-documental/permisos-documento/pm1/'),
    );
  });

  it('cierra el drawer', async () => {
    renderPage();
    await screen.findByText('factura.pdf');
    fireEvent.click(screen.getByRole('button', { name: 'Vínculos / Permisos' }));
    await screen.findByText('Vínculos');
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar detalle' }));
    await waitFor(() => expect(screen.queryByText('Vínculos')).not.toBeInTheDocument());
  });
});
