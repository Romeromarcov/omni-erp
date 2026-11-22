import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  API_URL: '/api',
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  fetchBlob: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'emp-1' }));

import { fetchBlob, get, post } from '../services/api';
import ConnectTarjetasPage from '../pages/Connect/ConnectTarjetasPage';
import { connectRoutes } from '../routes/connectRoutes';
import type { ConnectPerfil, ConnectTarjeta } from '../services/connectService';

const perfilesFixture: ConnectPerfil[] = [
  {
    id_perfil: 'perf-1',
    id_empresa: 'emp-1',
    usuario: 'usr-1',
    slug: 'ana-gomez',
    nombre_publico: 'Ana Gómez',
    cargo: 'Ventas',
    bio: '',
    telefono_publico: '',
    email_publico: 'ana@omni.com',
    tema: 'CLASICO',
    botones: [],
    plantilla_bloqueada: false,
    activo: true,
    fecha_creacion: '2026-11-01T10:00:00Z',
    fecha_actualizacion: '2026-11-01T10:00:00Z',
  },
];

const tarjetaInventario: ConnectTarjeta = {
  id_tarjeta: 'tarj-1',
  id_empresa: 'emp-1',
  perfil: null,
  perfil_slug: null,
  perfil_nombre: null,
  uid_chip: '04A1B2C3D4',
  tipo: 'PVC',
  estado: 'INVENTARIO',
  fecha_activacion: null,
  notas: 'Lote inicial',
  activo: true,
  fecha_creacion: '2026-11-20T10:00:00Z',
  fecha_actualizacion: '2026-11-20T10:00:00Z',
};

const tarjetaActiva: ConnectTarjeta = {
  id_tarjeta: 'tarj-2',
  id_empresa: 'emp-1',
  perfil: 'perf-1',
  perfil_slug: 'ana-gomez',
  perfil_nombre: 'Ana Gómez',
  uid_chip: '04DEADBEEF',
  tipo: 'METAL',
  estado: 'ACTIVA',
  fecha_activacion: '2026-11-20T12:00:00Z',
  notas: '',
  activo: true,
  fecha_creacion: '2026-11-20T10:00:00Z',
  fecha_actualizacion: '2026-11-20T12:00:00Z',
};

const tarjetaDesactivada: ConnectTarjeta = {
  ...tarjetaActiva,
  id_tarjeta: 'tarj-3',
  uid_chip: '04CAFEBABE',
  tipo: 'PULSERA',
  estado: 'DESACTIVADA',
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ConnectTarjetasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ConnectTarjetasPage', () => {
  const createObjectUrlMock = vi.fn();
  const revokeObjectUrlMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    let seq = 0;
    createObjectUrlMock.mockImplementation(() => `blob:mock-qr-${++seq}`);
    Object.defineProperty(URL, 'createObjectURL', {
      value: createObjectUrlMock,
      configurable: true,
      writable: true,
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: revokeObjectUrlMock,
      configurable: true,
      writable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lista tarjetas, filtra por estado e inactivas y maneja error de carga', async () => {
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/connect/perfiles/')) return perfilesFixture;
      return { results: [tarjetaInventario, tarjetaActiva, tarjetaDesactivada] };
    });

    renderPage();

    expect(await screen.findByText('04A1B2C3D4')).toBeInTheDocument();
    expect(screen.getByText('04DEADBEEF')).toBeInTheDocument();
    expect(screen.getByText('04CAFEBABE')).toBeInTheDocument();
    expect(screen.getByText('Tarjeta PVC')).toBeInTheDocument();
    expect(screen.getByText('Tarjeta metálica')).toBeInTheDocument();
    expect(screen.getByText('Pulsera NFC')).toBeInTheDocument();
    expect(screen.getByText('Sin asignar')).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByLabelText(/filtrar por estado/i));
    fireEvent.click(await screen.findByRole('option', { name: 'Activa' }));
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith('/connect/tarjetas/?empresa_id=emp-1&estado=ACTIVA');
    });

    fireEvent.click(screen.getByLabelText(/incluir inactivas/i));
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith(
        '/connect/tarjetas/?empresa_id=emp-1&estado=ACTIVA&incluir_inactivos=true',
      );
    });

    // Error al cargar tarjetas
    vi.mocked(get).mockRejectedValueOnce(new Error('Error al listar tarjetas'));
    renderPage();
    expect(await screen.findByText('Error al listar tarjetas')).toBeInTheDocument();
  });

  it('crea tarjeta en inventario, valida campos, muestra error backend y limpia el formulario al cerrar', async () => {
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/connect/perfiles/')) return perfilesFixture;
      return [tarjetaInventario];
    });
    vi.mocked(post)
      .mockRejectedValueOnce(new Error('UID duplicado'))
      .mockResolvedValueOnce({
        ...tarjetaInventario,
        id_tarjeta: 'tarj-nueva',
        uid_chip: '0411223344',
        tipo: 'METAL',
        notas: 'Entrega VIP',
      });

    renderPage();
    expect(await screen.findByText('04A1B2C3D4')).toBeInTheDocument();

    // Abrir diálogo y probar validación vacía
    fireEvent.click(screen.getByRole('button', { name: /nueva tarjeta/i }));
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /registrar tarjeta/i }));
    expect(await within(dialog).findByText(/el uid del chip es obligatorio/i)).toBeInTheDocument();

    // Llenar y cerrar para verificar reset
    fireEvent.change(within(dialog).getByLabelText(/uid del chip/i), {
      target: { value: '0499999999' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /cancelar/i }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    // Reabrir: el input debe estar limpio
    fireEvent.click(screen.getByRole('button', { name: /nueva tarjeta/i }));
    const dialog2 = screen.getByRole('dialog');
    expect(within(dialog2).getByLabelText(/uid del chip/i)).toHaveValue('');

    fireEvent.change(within(dialog2).getByLabelText(/uid del chip/i), {
      target: { value: '0411223344' },
    });
    fireEvent.mouseDown(within(dialog2).getByLabelText(/tipo de tarjeta/i));
    fireEvent.click(await screen.findByRole('option', { name: 'Tarjeta metálica' }));
    fireEvent.change(within(dialog2).getByLabelText(/^notas/i), {
      target: { value: 'Entrega VIP' },
    });

    // Primer intento falla con error de backend
    fireEvent.click(within(dialog2).getByRole('button', { name: /registrar tarjeta/i }));
    expect(await within(dialog2).findByText('UID duplicado')).toBeInTheDocument();

    // Segundo intento exitoso
    fireEvent.click(within(dialog2).getByRole('button', { name: /registrar tarjeta/i }));
    expect(await screen.findByText(/tarjeta 0411223344 registrada en inventario/i)).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith('/connect/tarjetas/', {
      uid_chip: '0411223344',
      tipo: 'METAL',
      notas: 'Entrega VIP',
      id_empresa: 'emp-1',
    });
  });

  it('ejecuta ciclo de vida completo: asignar, activar, desactivar y marcar perdida con confirmación', async () => {
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/connect/perfiles/')) return perfilesFixture;
      return [tarjetaInventario, tarjetaActiva, tarjetaDesactivada];
    });

    renderPage();
    expect(await screen.findByText('04A1B2C3D4')).toBeInTheDocument();

    // 1. Asignar tarjeta en inventario
    const filaInv = screen.getByText('04A1B2C3D4').closest('tr')!;
    fireEvent.click(within(filaInv).getByRole('button', { name: /asignar/i }));
    const asignarDialog = screen.getByRole('dialog');

    // Validación sin perfil seleccionado
    fireEvent.click(within(asignarDialog).getByRole('button', { name: /guardar asignación/i }));
    expect(
      await within(asignarDialog).findByText(/selecciona un perfil activo/i),
    ).toBeInTheDocument();

    // Seleccionar perfil y desmarcar activar inmediatamente
    fireEvent.mouseDown(within(asignarDialog).getByLabelText(/perfil connect/i));
    fireEvent.click(await screen.findByRole('option', { name: /Ana Gómez/i }));
    fireEvent.click(within(asignarDialog).getByLabelText(/activar tarjeta inmediatamente/i));

    vi.mocked(post)
      .mockRejectedValueOnce(new Error('Perfil inválido'))
      .mockResolvedValueOnce({ ...tarjetaInventario, perfil: 'perf-1' });
    fireEvent.click(within(asignarDialog).getByRole('button', { name: /guardar asignación/i }));
    expect(await within(asignarDialog).findByText('Perfil inválido')).toBeInTheDocument();

    fireEvent.click(within(asignarDialog).getByRole('button', { name: /guardar asignación/i }));
    expect(await screen.findByText(/tarjeta 04A1B2C3D4 asignada correctamente/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(post).toHaveBeenCalledWith('/connect/tarjetas/tarj-1/asignar/', {
      perfil_id: 'perf-1',
      activar: false,
    });

    // 2. Activar tarjeta desactivada (error y luego éxito)
    const filaDes = screen.getByText('04CAFEBABE').closest('tr')!;
    vi.mocked(post)
      .mockRejectedValueOnce(new Error('No se pudo activar'))
      .mockResolvedValueOnce({ ...tarjetaDesactivada, estado: 'ACTIVA' });

    fireEvent.click(within(filaDes).getByRole('button', { name: /^activar$/i }));
    expect(await screen.findByText('No se pudo activar')).toBeInTheDocument();

    fireEvent.click(within(filaDes).getByRole('button', { name: /^activar$/i }));
    expect(await screen.findByText(/tarjeta 04CAFEBABE activada/i)).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith('/connect/tarjetas/tarj-3/activar/', {});

    // 3. Desactivar tarjeta activa (error y luego éxito)
    const filaAct = screen.getByText('04DEADBEEF').closest('tr')!;
    vi.mocked(post)
      .mockRejectedValueOnce(new Error('No se pudo desactivar'))
      .mockResolvedValueOnce({ ...tarjetaActiva, estado: 'DESACTIVADA' });
    fireEvent.click(within(filaAct).getByRole('button', { name: /desactivar/i }));
    expect(await screen.findByText('No se pudo desactivar')).toBeInTheDocument();

    fireEvent.click(within(filaAct).getByRole('button', { name: /desactivar/i }));
    expect(await screen.findByText(/tarjeta 04DEADBEEF desactivada/i)).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith('/connect/tarjetas/tarj-2/desactivar/', {});

    // 4. Marcar perdida con confirmación (cancelar no llama API, error y luego éxito)
    fireEvent.click(within(filaAct).getByRole('button', { name: /marcar perdida/i }));
    const confirmDialog = screen.getByRole('dialog');
    expect(within(confirmDialog).getByText(/confirmar tarjeta perdida/i)).toBeInTheDocument();

    const callsBeforeCancel = vi.mocked(post).mock.calls.length;
    fireEvent.click(within(confirmDialog).getByRole('button', { name: /cancelar/i }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(vi.mocked(post).mock.calls.length).toBe(callsBeforeCancel);

    // Reabrir, probar error y luego confirmar
    fireEvent.click(within(filaAct).getByRole('button', { name: /marcar perdida/i }));
    const confirmDialog2 = screen.getByRole('dialog');
    vi.mocked(post)
      .mockRejectedValueOnce(new Error('Fallo al revocar'))
      .mockResolvedValueOnce({ ...tarjetaActiva, estado: 'PERDIDA' });
    fireEvent.click(within(confirmDialog2).getByRole('button', { name: /confirmar perdida/i }));
    expect(await within(confirmDialog2).findByText('Fallo al revocar')).toBeInTheDocument();

    fireEvent.click(within(confirmDialog2).getByRole('button', { name: /confirmar perdida/i }));

    expect(
      await screen.findByText(/tarjeta 04DEADBEEF marcada como perdida y revocada/i),
    ).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith('/connect/tarjetas/tarj-2/marcar-perdida/', {});
  });

  it('previsualiza y descarga QR SVG/PNG de tarjeta y mi-perfil revocando ObjectURL al cerrar y desmontar', async () => {
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/connect/perfiles/')) return perfilesFixture;
      return [tarjetaActiva];
    });
    vi.mocked(fetchBlob).mockResolvedValue(new Blob(['<svg></svg>'], { type: 'image/svg+xml' }));

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    const { unmount } = renderPage();
    expect(await screen.findByText('04DEADBEEF')).toBeInTheDocument();

    // QR de la tarjeta activa (SVG por defecto)
    const filaAct = screen.getByText('04DEADBEEF').closest('tr')!;
    fireEvent.click(within(filaAct).getByRole('button', { name: /^qr$/i }));

    const qrDialog = screen.getByRole('dialog');
    const img = await within(qrDialog).findByAltText(/vista previa qr tarjeta 04DEADBEEF/i);
    expect(img).toHaveAttribute('src', 'blob:mock-qr-1');
    expect(fetchBlob).toHaveBeenCalledWith('/connect/tarjetas/tarj-2/qr/?formato=svg', {
      headers: { Accept: 'image/svg+xml, application/json' },
    });

    // Descargar SVG (reutiliza previewUrl) y descargar PNG (fetchBlob png + revoca tempUrl diferido)
    fireEvent.click(within(qrDialog).getByRole('button', { name: /descargar svg/i }));
    expect(clickSpy).toHaveBeenCalledTimes(1);

    vi.mocked(fetchBlob).mockResolvedValueOnce(new Blob(['png-bytes'], { type: 'image/png' }));
    fireEvent.click(within(qrDialog).getByRole('button', { name: /descargar png/i }));
    await waitFor(() => {
      expect(fetchBlob).toHaveBeenCalledWith('/connect/tarjetas/tarj-2/qr/?formato=png', {
        headers: { Accept: 'image/png, application/json' },
      });
    });
    expect(clickSpy).toHaveBeenCalledTimes(2);
    await waitFor(
      () => {
        expect(revokeObjectUrlMock).toHaveBeenCalledWith('blob:mock-qr-2');
      },
      { timeout: 2000 },
    );

    // Cambiar vista previa a PNG revoca el URL anterior
    vi.mocked(fetchBlob).mockResolvedValueOnce(new Blob(['png-preview'], { type: 'image/png' }));
    fireEvent.click(within(qrDialog).getByRole('button', { name: /^png$/i }));
    await waitFor(() => {
      expect(revokeObjectUrlMock).toHaveBeenCalledWith('blob:mock-qr-1');
      expect(within(qrDialog).getByAltText(/vista previa qr tarjeta 04DEADBEEF/i)).toHaveAttribute(
        'src',
        'blob:mock-qr-3',
      );
    });

    // Cerrar diálogo revoca el preview activo
    fireEvent.click(within(qrDialog).getByRole('button', { name: /cerrar/i }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(revokeObjectUrlMock).toHaveBeenCalledWith('blob:mock-qr-3');

    // Abrir QR de mi perfil y probar error + luego éxito + revocación al desmontar
    vi.mocked(fetchBlob)
      .mockRejectedValueOnce(new Error('Aún no tienes perfil'))
      .mockResolvedValueOnce(new Blob(['<svg />'], { type: 'image/svg+xml' }));

    fireEvent.click(screen.getByRole('button', { name: /qr de mi perfil/i }));
    const qrPerfilDialog = screen.getByRole('dialog');
    expect(await within(qrPerfilDialog).findByText('Aún no tienes perfil')).toBeInTheDocument();
    expect(fetchBlob).toHaveBeenCalledWith('/connect/perfiles/mi-perfil/qr/?formato=svg&empresa_id=emp-1', {
      headers: { Accept: 'image/svg+xml, application/json' },
    });

    // Cambiar a PNG dispara segundo intento exitoso y luego desmontamos el árbol completo
    fireEvent.click(within(qrPerfilDialog).getByRole('button', { name: /^png$/i }));
    const imgPerfil = await within(qrPerfilDialog).findByAltText(/vista previa qr de mi perfil/i);
    expect(imgPerfil).toHaveAttribute('src', 'blob:mock-qr-4');

    unmount();
    expect(revokeObjectUrlMock).toHaveBeenCalledWith('blob:mock-qr-4');
  });

  it('monta /connect/tarjetas a través de connectRoutes y filtra perfil inactivo al abrir asignación', async () => {
    const tarjetaConPerfilInactivo: ConnectTarjeta = {
      ...tarjetaActiva,
      id_tarjeta: 'tarj-inact-perf',
      perfil: 'perf-inactivo',
      perfil_slug: 'viejo',
      perfil_nombre: 'Inactivo',
      estado: 'DESACTIVADA',
    };
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/connect/perfiles/')) {
        return [
          ...perfilesFixture,
          { ...perfilesFixture[0], id_perfil: 'perf-inactivo', activo: false },
        ];
      }
      return [tarjetaConPerfilInactivo];
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/connect/tarjetas']}>
          <Routes>{connectRoutes()}</Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('heading', { name: /tarjetas nfc y códigos qr/i })).toBeInTheDocument();
    const fila = (await screen.findByText('04DEADBEEF')).closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: /asignar/i }));
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /guardar asignación/i }));
    expect(await within(dialog).findByText(/selecciona un perfil activo/i)).toBeInTheDocument();
  });
});
