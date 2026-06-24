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
import SolicitudesAprobacionPage from '../pages/Aprobaciones/SolicitudesAprobacionPage';

const tipoApi = {
  id_tipo_aprobacion: 't1',
  id_empresa: 'e1',
  codigo_tipo: 'COMPRA',
  nombre_tipo: 'Aprobación de compra',
  modulo_origen: 'compras',
  activo: true,
};

const usuarioApi = {
  id: 'u1',
  username: 'ana',
  email: '',
  first_name: '',
  last_name: '',
  is_active: true,
  es_superusuario_omni: false,
};

const solicitudPendiente = {
  id_solicitud_aprobacion: 's1',
  id_tipo_aprobacion: 't1',
  id_entidad_origen: 'oc-1',
  nombre_modelo_origen: 'OrdenCompra',
  id_usuario_solicitante: 'u1',
  estado_solicitud: 'PENDIENTE',
  comentarios_solicitante: 'urge',
  etapa_actual_flujo: null,
};

const solicitudAprobada = {
  ...solicitudPendiente,
  id_solicitud_aprobacion: 's2',
  nombre_modelo_origen: 'Gasto',
  estado_solicitud: 'APROBADA',
};

const flujoApi = {
  id_flujo_aprobacion: 'f1',
  id_tipo_aprobacion: 't1',
  orden_etapa: 1,
  nombre_etapa: 'Jefatura',
  rol_aprobador: null,
  id_usuario_aprobador: null,
  monto_minimo: null,
  monto_maximo: null,
  activo: true,
};

const registroApi = {
  id_registro_aprobacion: 'r1',
  id_solicitud_aprobacion: 's1',
  id_flujo_aprobacion_etapa: 'f1',
  id_usuario_aprobador: 'u1',
  tipo_decision: 'APROBADO',
  comentarios: 'visto bueno',
  fecha_decision: '2026-06-24T10:00:00Z',
};

let solicitudesResult: unknown[] = [solicitudPendiente, solicitudAprobada];

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/gestion-aprobaciones/tipos-aprobacion')) return Promise.resolve([tipoApi]);
    if (url.startsWith('/gestion-aprobaciones/flujos-aprobacion')) return Promise.resolve([flujoApi]);
    if (url.startsWith('/gestion-aprobaciones/registros-aprobacion'))
      return Promise.resolve([registroApi]);
    if (url.startsWith('/gestion-aprobaciones/solicitudes-aprobacion'))
      return Promise.resolve(solicitudesResult);
    if (url.startsWith('/core/usuarios')) return Promise.resolve([usuarioApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SolicitudesAprobacionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SolicitudesAprobacionPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    solicitudesResult = [solicitudPendiente, solicitudAprobada];
    setupGet();
  });

  it('lista las solicitudes con tipo, solicitante y estado', async () => {
    renderPage();
    expect(await screen.findByText('OrdenCompra')).toBeInTheDocument();
    expect(screen.getAllByText('Aprobación de compra').length).toBeGreaterThan(0);
    expect(screen.getAllByText('ana').length).toBeGreaterThan(0);
    expect(screen.getByText('Pendiente')).toBeInTheDocument();
    expect(screen.getByText('Aprobada')).toBeInTheDocument();
  });

  it('filtra por estado y arma el querystring', async () => {
    renderPage();
    await screen.findByText('OrdenCompra');
    fireEvent.mouseDown(screen.getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'Aprobada' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        '/gestion-aprobaciones/solicitudes-aprobacion/?estado_solicitud=APROBADA',
      ),
    );
  });

  it('valida campos requeridos al crear', async () => {
    renderPage();
    await screen.findByText('OrdenCompra');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva solicitud' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete tipo, entidad de origen/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una solicitud enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_solicitud_aprobacion: 's3' });
    renderPage();
    await screen.findByText('OrdenCompra');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva solicitud' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Tipo de aprobación/));
    fireEvent.click(await screen.findByRole('option', { name: 'Aprobación de compra' }));
    fireEvent.change(within(dialog).getByLabelText(/Modelo de origen/), {
      target: { value: 'Nomina' },
    });
    fireEvent.change(within(dialog).getByLabelText(/ID de la entidad de origen/), {
      target: { value: 'nom-9' },
    });
    fireEvent.mouseDown(within(dialog).getByLabelText(/Solicitante/));
    fireEvent.click(await screen.findByRole('option', { name: 'ana' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/gestion-aprobaciones/solicitudes-aprobacion/',
        expect.objectContaining({
          id_tipo_aprobacion: 't1',
          nombre_modelo_origen: 'Nomina',
          id_entidad_origen: 'nom-9',
          id_usuario_solicitante: 'u1',
          estado_solicitud: 'PENDIENTE',
        }),
      ),
    );
  });

  it('edita una solicitud enviando el payload por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_solicitud_aprobacion: 's1' });
    renderPage();
    await screen.findByText('OrdenCompra');
    const fila = screen.getByText('OrdenCompra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    const modelo = await screen.findByLabelText(/Modelo de origen/);
    fireEvent.change(modelo, { target: { value: 'OrdenCompraEd' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/gestion-aprobaciones/solicitudes-aprobacion/s1/',
        expect.objectContaining({ nombre_modelo_origen: 'OrdenCompraEd' }),
      ),
    );
  });

  it('elimina una solicitud con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('OrdenCompra');
    const fila = screen.getByText('OrdenCompra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/gestion-aprobaciones/solicitudes-aprobacion/s1/'),
    );
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('OrdenCompra');
    const fila = screen.getByText('OrdenCompra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('abre el detalle y muestra el historial de decisiones', async () => {
    renderPage();
    await screen.findByText('OrdenCompra');
    const fila = screen.getByText('OrdenCompra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    expect(await screen.findByText('Solicitud OrdenCompra')).toBeInTheDocument();
    expect(await screen.findByText('visto bueno')).toBeInTheDocument();
    expect(screen.getByText('Historial de decisiones')).toBeInTheDocument();
  });

  it('valida etapa requerida al registrar una decisión', async () => {
    renderPage();
    await screen.findByText('OrdenCompra');
    const fila = screen.getByText('OrdenCompra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Registrar decisión' }));
    expect(await screen.findByText(/Seleccione la etapa del flujo/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('valida aprobador requerido al registrar una decisión', async () => {
    renderPage();
    await screen.findByText('OrdenCompra');
    const fila = screen.getByText('OrdenCompra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.mouseDown(await screen.findByLabelText(/Etapa del flujo/));
    fireEvent.click(await screen.findByRole('option', { name: /Jefatura/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Registrar decisión' }));
    expect(await screen.findByText(/Seleccione el usuario aprobador/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('registra una decisión: crea el registro y PATCH-ea el estado', async () => {
    vi.mocked(post).mockResolvedValue({ id_registro_aprobacion: 'r2' });
    vi.mocked(patch).mockResolvedValue({ id_solicitud_aprobacion: 's1', estado_solicitud: 'APROBADA' });
    renderPage();
    await screen.findByText('OrdenCompra');
    const fila = screen.getByText('OrdenCompra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.mouseDown(await screen.findByLabelText(/Etapa del flujo/));
    fireEvent.click(await screen.findByRole('option', { name: /Jefatura/ }));
    fireEvent.mouseDown(screen.getByLabelText(/Usuario aprobador/));
    fireEvent.click(await screen.findByRole('option', { name: 'ana' }));
    fireEvent.change(screen.getByLabelText(/Comentario/), { target: { value: 'aprobado ok' } });
    fireEvent.click(screen.getByRole('button', { name: 'Registrar decisión' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/gestion-aprobaciones/registros-aprobacion/',
        expect.objectContaining({
          id_solicitud_aprobacion: 's1',
          id_flujo_aprobacion_etapa: 'f1',
          id_usuario_aprobador: 'u1',
          tipo_decision: 'APROBADO',
          comentarios: 'aprobado ok',
        }),
      ),
    );
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/gestion-aprobaciones/solicitudes-aprobacion/s1/', {
        estado_solicitud: 'APROBADA',
      }),
    );
  });

  it('registra un rechazo y PATCH-ea el estado a RECHAZADA', async () => {
    vi.mocked(post).mockResolvedValue({ id_registro_aprobacion: 'r2' });
    vi.mocked(patch).mockResolvedValue({ id_solicitud_aprobacion: 's1', estado_solicitud: 'RECHAZADA' });
    renderPage();
    await screen.findByText('OrdenCompra');
    const fila = screen.getByText('OrdenCompra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.mouseDown(await screen.findByLabelText(/Etapa del flujo/));
    fireEvent.click(await screen.findByRole('option', { name: /Jefatura/ }));
    fireEvent.mouseDown(screen.getByLabelText(/Usuario aprobador/));
    fireEvent.click(await screen.findByRole('option', { name: 'ana' }));
    fireEvent.mouseDown(screen.getByLabelText(/Decisión/));
    fireEvent.click(await screen.findByRole('option', { name: 'Rechazado' }));
    fireEvent.click(screen.getByRole('button', { name: 'Registrar decisión' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/gestion-aprobaciones/solicitudes-aprobacion/s1/', {
        estado_solicitud: 'RECHAZADA',
      }),
    );
  });

  it('en una solicitud cerrada el detalle bloquea registrar decisión', async () => {
    renderPage();
    await screen.findByText('Gasto');
    const fila = screen.getByText('Gasto').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    expect(await screen.findByText(/no admite más decisiones/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Registrar decisión' })).not.toBeInTheDocument();
  });

  it('muestra error al fallar el registro de la decisión', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ error: 'Etapa inválida.' })));
    renderPage();
    await screen.findByText('OrdenCompra');
    const fila = screen.getByText('OrdenCompra').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.mouseDown(await screen.findByLabelText(/Etapa del flujo/));
    fireEvent.click(await screen.findByRole('option', { name: /Jefatura/ }));
    fireEvent.mouseDown(screen.getByLabelText(/Usuario aprobador/));
    fireEvent.click(await screen.findByRole('option', { name: 'ana' }));
    fireEvent.click(screen.getByRole('button', { name: 'Registrar decisión' }));
    expect(await screen.findByText(/Etapa inválida/)).toBeInTheDocument();
  });

  it('muestra error al fallar la creación', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ id_entidad_origen: ['inválido'] })));
    renderPage();
    await screen.findByText('OrdenCompra');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva solicitud' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText(/Tipo de aprobación/));
    fireEvent.click(await screen.findByRole('option', { name: 'Aprobación de compra' }));
    fireEvent.change(within(dialog).getByLabelText(/Modelo de origen/), { target: { value: 'X' } });
    fireEvent.change(within(dialog).getByLabelText(/ID de la entidad de origen/), {
      target: { value: 'bad' },
    });
    fireEvent.mouseDown(within(dialog).getByLabelText(/Solicitante/));
    fireEvent.click(await screen.findByRole('option', { name: 'ana' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/inválido/)).toBeInTheDocument();
  });
});
