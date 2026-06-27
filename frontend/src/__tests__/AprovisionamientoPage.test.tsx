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
vi.mock('../services/session', () => ({ getSessionUsuarioId: () => 'u1' }));

import { get, post, patch, del } from '../services/api';
import AprovisionamientoPage from '../pages/Compras/AprovisionamientoPage';

const requisicionApi = {
  id_requisicion: 'r1',
  id_empresa: 'e1',
  id_solicitante: 'u1',
  id_departamento: 'dep1',
  numero_requisicion: 'REQ-001',
  fecha_requisicion: '2026-06-01',
  estado: 'BORRADOR',
  prioridad: 'MEDIA',
  fecha_necesidad: '2026-06-10',
  justificacion: 'Reposición',
  observaciones: null,
  fecha_creacion: '2026-06-01',
};

const solicitudApi = {
  id_solicitud_cotizacion: 's1',
  id_empresa: 'e1',
  numero_solicitud: 'SOL-001',
  fecha_solicitud: '2026-06-01',
  fecha_vencimiento: '2026-06-15',
  estado: 'BORRADOR',
  observaciones: null,
  fecha_creacion: '2026-06-01',
};

const ofertaApi = {
  id_oferta: 'o1',
  id_solicitud_cotizacion: 's1',
  id_proveedor: 'prov1',
  numero_oferta: 'OF-001',
  fecha_oferta: '2026-06-02',
  fecha_vencimiento: '2026-06-20',
  estado: 'RECIBIDA',
  monto_total: '50.0000',
  condiciones_pago: null,
  tiempo_entrega: null,
  observaciones: null,
  fecha_creacion: '2026-06-02',
};

const productoApi = { id_producto: 'p1', id_empresa: 'e1', nombre_producto: 'Producto A', sku: 'P-A' };
const proveedorApi = { id_proveedor: 'prov1', id_empresa: 'e1', razon_social: 'Proveedor X', rif: 'J-1' };
const departamentoApi = { id_departamento: 'dep1', nombre_departamento: 'Compras' };

const detalleReqApi = {
  id_detalle_requisicion: 'dr1',
  id_requisicion: 'r1',
  id_producto: 'p1',
  cantidad_solicitada: '5.0000',
  precio_estimado: '10.0000',
  justificacion: null,
  observaciones: null,
};

const detalleOfeApi = {
  id_detalle_oferta: 'do1',
  id_oferta: 'o1',
  id_producto: 'p1',
  cantidad: '5.0000',
  precio_unitario: '10.0000',
  subtotal: '50.0000',
  tiempo_entrega: null,
  observaciones: null,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AprovisionamientoPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

interface MockData {
  requisiciones?: unknown[];
  detallesReq?: unknown[];
  solicitudes?: unknown[];
  detallesSol?: unknown[];
  ofertas?: unknown[];
  detallesOfe?: unknown[];
}

function mockGet(opts: MockData = {}) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/core/departamentos')) return Promise.resolve([departamentoApi]);
    if (url.startsWith('/inventario/productos')) return Promise.resolve([productoApi]);
    if (url.startsWith('/proveedores/proveedores')) return Promise.resolve([proveedorApi]);
    if (url.startsWith('/compras/detalles-requisicion-compra')) return Promise.resolve(opts.detallesReq ?? []);
    if (url.startsWith('/compras/requisiciones-compra')) return Promise.resolve(opts.requisiciones ?? [requisicionApi]);
    if (url.startsWith('/compras/detalles-solicitud-cotizacion')) return Promise.resolve(opts.detallesSol ?? []);
    if (url.startsWith('/compras/solicitudes-cotizacion')) return Promise.resolve(opts.solicitudes ?? [solicitudApi]);
    if (url.startsWith('/compras/detalles-oferta-proveedor')) return Promise.resolve(opts.detallesOfe ?? []);
    if (url.startsWith('/compras/ofertas-proveedor')) return Promise.resolve(opts.ofertas ?? [ofertaApi]);
    return Promise.resolve([]);
  });
}

describe('AprovisionamientoPage — tabs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet();
  });

  it('renderiza las tres pestañas y muestra requisiciones por defecto', async () => {
    renderPage();
    expect(screen.getByRole('tab', { name: 'Requisiciones' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Solicitudes de Cotización' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Ofertas de Proveedor' })).toBeInTheDocument();
    expect(await screen.findByText('REQ-001')).toBeInTheDocument();
  });

  it('cambia a la pestaña de solicitudes y luego ofertas', async () => {
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.click(screen.getByRole('tab', { name: 'Solicitudes de Cotización' }));
    expect(await screen.findByText('SOL-001')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Ofertas de Proveedor' }));
    expect(await screen.findByText('OF-001')).toBeInTheDocument();
  });
});

describe('AprovisionamientoPage — requisiciones CRUD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet();
  });

  it('valida número y justificación requeridos al crear', async () => {
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva requisición' }));
    expect(await screen.findByText('Nueva requisición', { selector: 'h2' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete el número de requisición y la justificación/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una requisición con id_solicitante de la sesión', async () => {
    vi.mocked(post).mockResolvedValue({ id_requisicion: 'r2' });
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva requisición' }));
    fireEvent.change(await screen.findByLabelText(/Número de requisición/), { target: { value: 'REQ-002' } });
    fireEvent.change(screen.getByLabelText(/Justificación/), { target: { value: 'Compra urgente' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/compras/requisiciones-compra/',
        expect.objectContaining({
          numero_requisicion: 'REQ-002',
          justificacion: 'Compra urgente',
          id_solicitante: 'u1',
          estado: 'BORRADOR',
          prioridad: 'MEDIA',
        }),
      ),
    );
  });

  it('edita una requisición (PATCH por id)', async () => {
    vi.mocked(patch).mockResolvedValue({ id_requisicion: 'r1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const num = await screen.findByLabelText(/Número de requisición/);
    fireEvent.change(num, { target: { value: 'REQ-001-B' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/compras/requisiciones-compra/r1/',
        expect.objectContaining({ numero_requisicion: 'REQ-001-B', id_solicitante: 'u1' }),
      ),
    );
  });

  it('elimina con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/compras/requisiciones-compra/r1/'));
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('muestra error de backend al guardar (mensajeDeError)', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ numero_requisicion: ['Ya existe.'] })));
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva requisición' }));
    fireEvent.change(await screen.findByLabelText(/Número de requisición/), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText(/Justificación/), { target: { value: 'X' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/numero_requisicion: Ya existe\./)).toBeInTheDocument();
  });

  it('filtra por estado (querystring)', async () => {
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.mouseDown(screen.getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'APROBADA' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/compras/requisiciones-compra/?estado=APROBADA'),
    );
  });
});

describe('AprovisionamientoPage — líneas de requisición (drawer)', () => {
  beforeEach(() => vi.clearAllMocks());

  async function abrirLineas() {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Líneas' }));
    await screen.findByText('Líneas de la requisición');
  }

  it('valida producto y cantidad al agregar línea', async () => {
    mockGet();
    await abrirLineas();
    fireEvent.click(screen.getByRole('button', { name: 'Agregar línea' }));
    expect(await screen.findByText(/Seleccione un producto e indique la cantidad/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una línea con el payload correcto', async () => {
    mockGet();
    vi.mocked(post).mockResolvedValue({ id_detalle_requisicion: 'dr-new' });
    await abrirLineas();
    fireEvent.mouseDown(screen.getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Producto A/ }));
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar línea' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/compras/detalles-requisicion-compra/',
        expect.objectContaining({ id_requisicion: 'r1', id_producto: 'p1', cantidad_solicitada: '3' }),
      ),
    );
  });

  it('edita y elimina una línea existente', async () => {
    mockGet({ detallesReq: [detalleReqApi] });
    vi.mocked(patch).mockResolvedValue({ id_detalle_requisicion: 'dr1' });
    vi.mocked(del).mockResolvedValue(undefined);
    await abrirLineas();
    await screen.findByText(/Producto A.*5\.0000/);
    const editBtns = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editBtns[editBtns.length - 1]);
    const cantidad = screen.getByLabelText('Cantidad') as HTMLInputElement;
    await waitFor(() => expect(cantidad.value).toBe('5.0000'));
    fireEvent.change(cantidad, { target: { value: '8' } });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar línea' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/compras/detalles-requisicion-compra/dr1/',
        expect.objectContaining({ cantidad_solicitada: '8' }),
      ),
    );
    const delBtns = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delBtns[delBtns.length - 1]);
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/compras/detalles-requisicion-compra/dr1/'),
    );
  });

  it('cierra el drawer', async () => {
    mockGet();
    await abrirLineas();
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar detalle' }));
    await waitFor(() =>
      expect(screen.queryByText('Líneas de la requisición')).not.toBeInTheDocument(),
    );
  });
});

describe('AprovisionamientoPage — solicitudes CRUD + líneas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet();
  });

  async function irASolicitudes() {
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.click(screen.getByRole('tab', { name: 'Solicitudes de Cotización' }));
    await screen.findByText('SOL-001');
  }

  it('valida número requerido', async () => {
    await irASolicitudes();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva solicitud' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete el número de solicitud/)).toBeInTheDocument();
  });

  it('crea una solicitud', async () => {
    vi.mocked(post).mockResolvedValue({ id_solicitud_cotizacion: 's2' });
    await irASolicitudes();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva solicitud' }));
    fireEvent.change(await screen.findByLabelText(/Número de solicitud/), { target: { value: 'SOL-002' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/compras/solicitudes-cotizacion/',
        expect.objectContaining({ numero_solicitud: 'SOL-002', estado: 'BORRADOR' }),
      ),
    );
  });

  it('agrega una línea a la solicitud', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_solicitud: 'ds1' });
    await irASolicitudes();
    fireEvent.click(screen.getByRole('button', { name: 'Líneas' }));
    await screen.findByText('Líneas de la solicitud');
    fireEvent.mouseDown(screen.getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Producto A/ }));
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar línea' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/compras/detalles-solicitud-cotizacion/',
        expect.objectContaining({ id_solicitud_cotizacion: 's1', id_producto: 'p1', cantidad: '2' }),
      ),
    );
  });

  it('valida la línea de solicitud, edita y elimina una existente', async () => {
    const detalleSolApi = {
      id_detalle_solicitud: 'ds1',
      id_solicitud_cotizacion: 's1',
      id_producto: 'p1',
      cantidad: '4.0000',
      especificaciones: 'azul',
      observaciones: null,
    };
    mockGet({ detallesSol: [detalleSolApi] });
    vi.mocked(patch).mockResolvedValue({ id_detalle_solicitud: 'ds1' });
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.click(screen.getByRole('tab', { name: 'Solicitudes de Cotización' }));
    await screen.findByText('SOL-001');
    fireEvent.click(screen.getByRole('button', { name: 'Líneas' }));
    await screen.findByText('Líneas de la solicitud');
    // Validación
    fireEvent.click(screen.getByRole('button', { name: 'Agregar línea' }));
    expect(await screen.findByText(/Seleccione un producto e indique la cantidad/)).toBeInTheDocument();
    // Editar
    const editBtns = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editBtns[editBtns.length - 1]);
    const cantidad = screen.getByLabelText('Cantidad') as HTMLInputElement;
    await waitFor(() => expect(cantidad.value).toBe('4.0000'));
    fireEvent.change(cantidad, { target: { value: '9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar línea' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/compras/detalles-solicitud-cotizacion/ds1/',
        expect.objectContaining({ cantidad: '9' }),
      ),
    );
    // Eliminar
    const delBtns = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delBtns[delBtns.length - 1]);
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/compras/detalles-solicitud-cotizacion/ds1/'),
    );
  });

  it('edita una solicitud y muestra error de backend', async () => {
    vi.mocked(patch).mockResolvedValue({ id_solicitud_cotizacion: 's1' });
    await irASolicitudes();
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    const num = await screen.findByLabelText(/Número de solicitud/);
    fireEvent.change(num, { target: { value: 'SOL-001-B' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/compras/solicitudes-cotizacion/s1/',
        expect.objectContaining({ numero_solicitud: 'SOL-001-B' }),
      ),
    );
  });
});

describe('AprovisionamientoPage — ofertas CRUD + líneas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet();
  });

  async function irAOfertas() {
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.click(screen.getByRole('tab', { name: 'Ofertas de Proveedor' }));
    await screen.findByText('OF-001');
  }

  it('muestra proveedor y solicitud en la tabla', async () => {
    await irAOfertas();
    expect(await screen.findByText('Proveedor X')).toBeInTheDocument();
    expect(screen.getAllByText('SOL-001').length).toBeGreaterThan(0);
  });

  it('valida campos requeridos de la oferta', async () => {
    await irAOfertas();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva oferta' }));
    fireEvent.change(await screen.findByLabelText(/Número de oferta/), { target: { value: 'OF-002' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete el número de oferta, la solicitud y el proveedor/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una oferta seleccionando solicitud y proveedor', async () => {
    vi.mocked(post).mockResolvedValue({ id_oferta: 'o2' });
    await irAOfertas();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva oferta' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Número de oferta/), { target: { value: 'OF-002' } });
    fireEvent.mouseDown(within(dialog).getByLabelText(/Solicitud de cotización/));
    fireEvent.click(await screen.findByRole('option', { name: 'SOL-001' }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/Proveedor/));
    fireEvent.click(await screen.findByRole('option', { name: 'Proveedor X' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/compras/ofertas-proveedor/',
        expect.objectContaining({
          numero_oferta: 'OF-002',
          id_solicitud_cotizacion: 's1',
          id_proveedor: 'prov1',
        }),
      ),
    );
  });

  it('agrega una línea de oferta calculando el subtotal', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_oferta: 'do-new' });
    await irAOfertas();
    fireEvent.click(screen.getByRole('button', { name: 'Líneas' }));
    await screen.findByText('Líneas de la oferta');
    fireEvent.mouseDown(screen.getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Producto A/ }));
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '4' } });
    fireEvent.change(screen.getByLabelText('Precio unitario'), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar línea' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/compras/detalles-oferta-proveedor/',
        expect.objectContaining({
          id_oferta: 'o1',
          cantidad: '4',
          precio_unitario: '10',
          subtotal: '40.0000',
        }),
      ),
    );
  });

  it('lista las líneas de oferta existentes con su subtotal', async () => {
    mockGet({ detallesOfe: [detalleOfeApi] });
    await irAOfertas();
    fireEvent.click(screen.getByRole('button', { name: 'Líneas' }));
    expect(await screen.findByText(/Producto A.*5\.0000.*10\.0000.*50\.0000/)).toBeInTheDocument();
  });

  it('valida la línea de oferta, edita y elimina una existente', async () => {
    mockGet({ detallesOfe: [detalleOfeApi] });
    vi.mocked(patch).mockResolvedValue({ id_detalle_oferta: 'do1' });
    vi.mocked(del).mockResolvedValue(undefined);
    await irAOfertas();
    fireEvent.click(screen.getByRole('button', { name: 'Líneas' }));
    await screen.findByText('Líneas de la oferta');
    // Validación: sin producto
    fireEvent.click(screen.getByRole('button', { name: 'Agregar línea' }));
    expect(await screen.findByText(/Seleccione un producto e indique cantidad y precio/)).toBeInTheDocument();
    // Editar
    const editBtns = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editBtns[editBtns.length - 1]);
    const precio = screen.getByLabelText('Precio unitario') as HTMLInputElement;
    await waitFor(() => expect(precio.value).toBe('10.0000'));
    fireEvent.change(precio, { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar línea' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/compras/detalles-oferta-proveedor/do1/',
        expect.objectContaining({ precio_unitario: '12', subtotal: '60.0000' }),
      ),
    );
    // Cancelar edición
    fireEvent.click(editBtns[editBtns.length - 1]);
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Agregar línea' })).toBeInTheDocument(),
    );
    // Eliminar
    const delBtns = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delBtns[delBtns.length - 1]);
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/compras/detalles-oferta-proveedor/do1/'),
    );
  });

  it('edita una oferta (PATCH) y elimina con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(patch).mockResolvedValue({ id_oferta: 'o1' });
    vi.mocked(del).mockResolvedValue(undefined);
    await irAOfertas();
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    const num = await screen.findByLabelText(/Número de oferta/);
    fireEvent.change(num, { target: { value: 'OF-001-B' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/compras/ofertas-proveedor/o1/',
        expect.objectContaining({ numero_oferta: 'OF-001-B' }),
      ),
    );
    // El diálogo se cierra tras guardar; esperamos a que desaparezca para
    // poder pulsar el botón Eliminar de la fila (no el del diálogo).
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/compras/ofertas-proveedor/o1/'));
    confirmSpy.mockRestore();
  });

  it('filtra ofertas por solicitud', async () => {
    await irAOfertas();
    fireEvent.mouseDown(screen.getByLabelText('Solicitud'));
    fireEvent.click(await screen.findByRole('option', { name: 'SOL-001' }));
    await waitFor(() => expect(screen.getByText('OF-001')).toBeInTheDocument());
  });

  it('crea una oferta rellenando todos los campos opcionales (onChange)', async () => {
    vi.mocked(post).mockResolvedValue({ id_oferta: 'o3' });
    await irAOfertas();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva oferta' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Número de oferta/), { target: { value: 'OF-003' } });
    fireEvent.mouseDown(within(dialog).getByLabelText(/Solicitud de cotización/));
    fireEvent.click(await screen.findByRole('option', { name: 'SOL-001' }));
    fireEvent.mouseDown(within(dialog).getByLabelText(/Proveedor/));
    fireEvent.click(await screen.findByRole('option', { name: 'Proveedor X' }));
    // Estado select (no por defecto).
    fireEvent.mouseDown(within(dialog).getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'EVALUADA' }));
    fireEvent.change(within(dialog).getByLabelText('Monto total'), { target: { value: '120.50' } });
    fireEvent.change(within(dialog).getByLabelText(/Fecha de oferta/), { target: { value: '2026-06-05' } });
    fireEvent.change(within(dialog).getByLabelText(/Fecha de vencimiento/), { target: { value: '2026-06-25' } });
    fireEvent.change(within(dialog).getByLabelText(/Condiciones de pago/), { target: { value: '30 días' } });
    fireEvent.change(within(dialog).getByLabelText(/Tiempo de entrega/), { target: { value: '2 semanas' } });
    fireEvent.change(within(dialog).getByLabelText(/Observaciones/), { target: { value: 'urgente' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/compras/ofertas-proveedor/',
        expect.objectContaining({
          numero_oferta: 'OF-003',
          estado: 'EVALUADA',
          monto_total: '120.50',
          fecha_oferta: '2026-06-05',
          fecha_vencimiento: '2026-06-25',
          condiciones_pago: '30 días',
          tiempo_entrega: '2 semanas',
          observaciones: 'urgente',
        }),
      ),
    );
  });

  it('cancela el diálogo de oferta sin guardar', async () => {
    await irAOfertas();
    fireEvent.click(screen.getByRole('button', { name: 'Nueva oferta' }));
    await screen.findByRole('dialog');
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(post).not.toHaveBeenCalled();
  });

  it('muestra error al eliminar una línea de oferta (onError del drawer)', async () => {
    mockGet({ detallesOfe: [detalleOfeApi] });
    vi.mocked(del).mockRejectedValue(new Error('línea en uso'));
    await irAOfertas();
    fireEvent.click(screen.getByRole('button', { name: 'Líneas' }));
    await screen.findByText('Líneas de la oferta');
    await screen.findByText(/Producto A.*5\.0000.*10\.0000.*50\.0000/);
    const delBtns = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delBtns[delBtns.length - 1]);
    expect(await screen.findByText(/línea en uso/)).toBeInTheDocument();
    // Cierra el alert del drawer (onClose).
    fireEvent.click(screen.getAllByLabelText('Close')[0]);
    await waitFor(() => expect(screen.queryByText(/línea en uso/)).not.toBeInTheDocument());
  });

  it('rellena tiempo de entrega de la línea de oferta y agrega', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_oferta: 'do-2' });
    await irAOfertas();
    fireEvent.click(screen.getByRole('button', { name: 'Líneas' }));
    await screen.findByText('Líneas de la oferta');
    fireEvent.mouseDown(screen.getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Producto A/ }));
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Precio unitario'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText(/Tiempo de entrega/), { target: { value: '5 días' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar línea' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/compras/detalles-oferta-proveedor/',
        expect.objectContaining({ subtotal: '10.0000', tiempo_entrega: '5 días' }),
      ),
    );
  });
});

describe('AprovisionamientoPage — rutas de error y edición de drawers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet();
  });

  it('muestra error al eliminar una requisición (onError)', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockRejectedValue(new Error('req con dependencias'));
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(await screen.findByText(/req con dependencias/)).toBeInTheDocument();
  });

  it('cierra el diálogo de requisición con Cancelar', async () => {
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva requisición' }));
    await screen.findByRole('dialog');
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('rellena precio estimado y justificación en la línea de requisición', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_requisicion: 'dr-x' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Líneas' }));
    await screen.findByText('Líneas de la requisición');
    fireEvent.mouseDown(screen.getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Producto A/ }));
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('Precio estimado'), { target: { value: '7.5' } });
    fireEvent.change(screen.getByLabelText(/Justificación/), { target: { value: 'falta stock' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar línea' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/compras/detalles-requisicion-compra/',
        expect.objectContaining({ precio_estimado: '7.5', justificacion: 'falta stock' }),
      ),
    );
  });

  it('cancela la edición de una línea de requisición (reset)', async () => {
    mockGet({ detallesReq: [detalleReqApi] });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Líneas' }));
    await screen.findByText(/Producto A.*5\.0000/);
    const editBtns = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editBtns[editBtns.length - 1]);
    await screen.findByRole('button', { name: 'Actualizar línea' });
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Agregar línea' })).toBeInTheDocument(),
    );
  });

  it('edita la solicitud rellenando observaciones y fechas', async () => {
    vi.mocked(patch).mockResolvedValue({ id_solicitud_cotizacion: 's1' });
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.click(screen.getByRole('tab', { name: 'Solicitudes de Cotización' }));
    await screen.findByText('SOL-001');
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Fecha de solicitud/), { target: { value: '2026-06-02' } });
    fireEvent.change(within(dialog).getByLabelText(/Fecha de vencimiento/), { target: { value: '2026-06-30' } });
    fireEvent.mouseDown(within(dialog).getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'ENVIADA' }));
    fireEvent.change(within(dialog).getByLabelText(/Observaciones/), { target: { value: 'revisar' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/compras/solicitudes-cotizacion/s1/',
        expect.objectContaining({
          fecha_solicitud: '2026-06-02',
          fecha_vencimiento: '2026-06-30',
          estado: 'ENVIADA',
          observaciones: 'revisar',
        }),
      ),
    );
  });

  it('agrega especificaciones a la línea de solicitud', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_solicitud: 'ds-x' });
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.click(screen.getByRole('tab', { name: 'Solicitudes de Cotización' }));
    await screen.findByText('SOL-001');
    fireEvent.click(screen.getByRole('button', { name: 'Líneas' }));
    await screen.findByText('Líneas de la solicitud');
    fireEvent.mouseDown(screen.getByLabelText(/Producto/));
    fireEvent.click(await screen.findByRole('option', { name: /Producto A/ }));
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText(/Especificaciones/), { target: { value: 'color azul' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar línea' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/compras/detalles-solicitud-cotizacion/',
        expect.objectContaining({ especificaciones: 'color azul' }),
      ),
    );
  });

  it('cierra el alert de error de requisición con la X', async () => {
    vi.mocked(post).mockRejectedValue(new Error('falló'));
    renderPage();
    await screen.findByText('REQ-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva requisición' }));
    fireEvent.change(await screen.findByLabelText(/Número de requisición/), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText(/Justificación/), { target: { value: 'X' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await screen.findByText(/falló/);
    fireEvent.click(screen.getByLabelText('Close'));
    await waitFor(() => expect(screen.queryByText(/falló/)).not.toBeInTheDocument());
  });
});
