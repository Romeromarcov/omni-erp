import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  requisicionesService,
  detallesRequisicionService,
  solicitudesCotizacionService,
  detallesSolicitudService,
  ofertasProveedorService,
  detallesOfertaService,
  type RequisicionCompraPayload,
  type DetalleRequisicionPayload,
  type SolicitudCotizacionPayload,
  type DetalleSolicitudPayload,
  type OfertaProveedorPayload,
  type DetalleOfertaPayload,
} from '../services/aprovisionamientoService';

const reqPayload: RequisicionCompraPayload = {
  id_solicitante: 'u1',
  id_departamento: 'dep1',
  numero_requisicion: 'REQ-001',
  fecha_requisicion: '2026-06-01',
  estado: 'BORRADOR',
  prioridad: 'MEDIA',
  fecha_necesidad: '2026-06-10',
  justificacion: 'Reposición',
  observaciones: null,
};

const detReqPayload: DetalleRequisicionPayload = {
  id_requisicion: 'r1',
  id_producto: 'p1',
  cantidad_solicitada: '5.0000',
  precio_estimado: '10.0000',
  justificacion: null,
  observaciones: null,
};

const solPayload: SolicitudCotizacionPayload = {
  numero_solicitud: 'SOL-001',
  fecha_solicitud: '2026-06-01',
  fecha_vencimiento: '2026-06-15',
  estado: 'BORRADOR',
  observaciones: null,
};

const detSolPayload: DetalleSolicitudPayload = {
  id_solicitud_cotizacion: 's1',
  id_producto: 'p1',
  cantidad: '5.0000',
  especificaciones: 'rojo',
  observaciones: null,
};

const ofePayload: OfertaProveedorPayload = {
  id_solicitud_cotizacion: 's1',
  id_proveedor: 'prov1',
  numero_oferta: 'OF-001',
  fecha_oferta: '2026-06-02',
  fecha_vencimiento: '2026-06-20',
  estado: 'RECIBIDA',
  monto_total: '50.0000',
  condiciones_pago: '30 días',
  tiempo_entrega: '1 semana',
  observaciones: null,
};

const detOfePayload: DetalleOfertaPayload = {
  id_oferta: 'o1',
  id_producto: 'p1',
  cantidad: '5.0000',
  precio_unitario: '10.0000',
  subtotal: '50.0000',
  tiempo_entrega: null,
  observaciones: null,
};

describe('requisicionesService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma querystring con estado (rama paginada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_requisicion: 'r1' }] });
    const r = await requisicionesService.getAll({ estado: 'APROBADA' });
    expect(get).toHaveBeenCalledWith('/compras/requisiciones-compra/?estado=APROBADA');
    expect(r).toEqual([{ id_requisicion: 'r1' }]);
  });

  it('getAll sin parámetros pega al endpoint base (rama array)', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_requisicion: 'r1' }]);
    const r = await requisicionesService.getAll();
    expect(get).toHaveBeenCalledWith('/compras/requisiciones-compra/');
    expect(r).toHaveLength(1);
  });

  it('getAll normaliza una respuesta vacía/no reconocida', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    const r = await requisicionesService.getAll({ estado: '' });
    // estado vacío no agrega querystring
    expect(get).toHaveBeenCalledWith('/compras/requisiciones-compra/');
    expect(r).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_requisicion: 'r1' });
    await requisicionesService.getById('r1');
    expect(get).toHaveBeenCalledWith('/compras/requisiciones-compra/r1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_requisicion: 'r2' });
    await requisicionesService.create(reqPayload);
    expect(post).toHaveBeenCalledWith('/compras/requisiciones-compra/', reqPayload);

    vi.mocked(patch).mockResolvedValue({ id_requisicion: 'r1' });
    await requisicionesService.update('r1', reqPayload);
    expect(patch).toHaveBeenCalledWith('/compras/requisiciones-compra/r1/', reqPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await requisicionesService.remove('r1');
    expect(del).toHaveBeenCalledWith('/compras/requisiciones-compra/r1/');
  });
});

describe('detallesRequisicionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll filtra por requisición en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_detalle_requisicion: 'd1', id_requisicion: 'r1' },
      { id_detalle_requisicion: 'd2', id_requisicion: 'otra' },
    ]);
    const r = await detallesRequisicionService.getAll({ requisicion: 'r1' });
    expect(get).toHaveBeenCalledWith('/compras/detalles-requisicion-compra/');
    expect(r.map((d) => d.id_detalle_requisicion)).toEqual(['d1']);
  });

  it('getAll sin filtro devuelve todo (rama paginada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_detalle_requisicion: 'd1', id_requisicion: 'r1' }] });
    const r = await detallesRequisicionService.getAll();
    expect(r).toHaveLength(1);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_requisicion: 'd1' });
    await detallesRequisicionService.create(detReqPayload);
    expect(post).toHaveBeenCalledWith('/compras/detalles-requisicion-compra/', detReqPayload);

    vi.mocked(patch).mockResolvedValue({ id_detalle_requisicion: 'd1' });
    await detallesRequisicionService.update('d1', detReqPayload);
    expect(patch).toHaveBeenCalledWith('/compras/detalles-requisicion-compra/d1/', detReqPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await detallesRequisicionService.remove('d1');
    expect(del).toHaveBeenCalledWith('/compras/detalles-requisicion-compra/d1/');
  });
});

describe('solicitudesCotizacionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma querystring con estado', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_solicitud_cotizacion: 's1' }]);
    await solicitudesCotizacionService.getAll({ estado: 'ENVIADA' });
    expect(get).toHaveBeenCalledWith('/compras/solicitudes-cotizacion/?estado=ENVIADA');
  });

  it('getAll sin parámetros + getById', async () => {
    vi.mocked(get).mockResolvedValue({ results: [] });
    await solicitudesCotizacionService.getAll();
    expect(get).toHaveBeenCalledWith('/compras/solicitudes-cotizacion/');
    await solicitudesCotizacionService.getById('s1');
    expect(get).toHaveBeenCalledWith('/compras/solicitudes-cotizacion/s1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_solicitud_cotizacion: 's2' });
    await solicitudesCotizacionService.create(solPayload);
    expect(post).toHaveBeenCalledWith('/compras/solicitudes-cotizacion/', solPayload);

    vi.mocked(patch).mockResolvedValue({ id_solicitud_cotizacion: 's1' });
    await solicitudesCotizacionService.update('s1', solPayload);
    expect(patch).toHaveBeenCalledWith('/compras/solicitudes-cotizacion/s1/', solPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await solicitudesCotizacionService.remove('s1');
    expect(del).toHaveBeenCalledWith('/compras/solicitudes-cotizacion/s1/');
  });
});

describe('detallesSolicitudService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll filtra por solicitud en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_detalle_solicitud: 'd1', id_solicitud_cotizacion: 's1' },
      { id_detalle_solicitud: 'd2', id_solicitud_cotizacion: 'otra' },
    ]);
    const r = await detallesSolicitudService.getAll({ solicitud: 's1' });
    expect(r.map((d) => d.id_detalle_solicitud)).toEqual(['d1']);
  });

  it('getAll sin filtro (rama array vacía)', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    const r = await detallesSolicitudService.getAll();
    expect(r).toEqual([]);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_solicitud: 'd1' });
    await detallesSolicitudService.create(detSolPayload);
    expect(post).toHaveBeenCalledWith('/compras/detalles-solicitud-cotizacion/', detSolPayload);

    vi.mocked(patch).mockResolvedValue({ id_detalle_solicitud: 'd1' });
    await detallesSolicitudService.update('d1', detSolPayload);
    expect(patch).toHaveBeenCalledWith('/compras/detalles-solicitud-cotizacion/d1/', detSolPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await detallesSolicitudService.remove('d1');
    expect(del).toHaveBeenCalledWith('/compras/detalles-solicitud-cotizacion/d1/');
  });
});

describe('ofertasProveedorService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma querystring con estado y filtra por solicitud en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_oferta: 'o1', id_solicitud_cotizacion: 's1' },
      { id_oferta: 'o2', id_solicitud_cotizacion: 'otra' },
    ]);
    const r = await ofertasProveedorService.getAll({ estado: 'RECIBIDA', solicitud: 's1' });
    expect(get).toHaveBeenCalledWith('/compras/ofertas-proveedor/?estado=RECIBIDA');
    expect(r.map((o) => o.id_oferta)).toEqual(['o1']);
  });

  it('getAll sin parámetros (rama paginada) + getById', async () => {
    vi.mocked(get).mockResolvedValue({ results: [{ id_oferta: 'o1', id_solicitud_cotizacion: 's1' }] });
    const r = await ofertasProveedorService.getAll();
    expect(get).toHaveBeenCalledWith('/compras/ofertas-proveedor/');
    expect(r).toHaveLength(1);
    await ofertasProveedorService.getById('o1');
    expect(get).toHaveBeenCalledWith('/compras/ofertas-proveedor/o1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_oferta: 'o2' });
    await ofertasProveedorService.create(ofePayload);
    expect(post).toHaveBeenCalledWith('/compras/ofertas-proveedor/', ofePayload);

    vi.mocked(patch).mockResolvedValue({ id_oferta: 'o1' });
    await ofertasProveedorService.update('o1', ofePayload);
    expect(patch).toHaveBeenCalledWith('/compras/ofertas-proveedor/o1/', ofePayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await ofertasProveedorService.remove('o1');
    expect(del).toHaveBeenCalledWith('/compras/ofertas-proveedor/o1/');
  });

  it('propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ detail: 'Falló' })));
    await expect(ofertasProveedorService.create(ofePayload)).rejects.toThrow();
  });
});

describe('detallesOfertaService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll filtra por oferta en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_detalle_oferta: 'd1', id_oferta: 'o1' },
      { id_detalle_oferta: 'd2', id_oferta: 'otra' },
    ]);
    const r = await detallesOfertaService.getAll({ oferta: 'o1' });
    expect(r.map((d) => d.id_detalle_oferta)).toEqual(['d1']);
  });

  it('getAll sin filtro (rama vacía/no reconocida)', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    const r = await detallesOfertaService.getAll();
    expect(r).toEqual([]);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_oferta: 'd1' });
    await detallesOfertaService.create(detOfePayload);
    expect(post).toHaveBeenCalledWith('/compras/detalles-oferta-proveedor/', detOfePayload);

    vi.mocked(patch).mockResolvedValue({ id_detalle_oferta: 'd1' });
    await detallesOfertaService.update('d1', detOfePayload);
    expect(patch).toHaveBeenCalledWith('/compras/detalles-oferta-proveedor/d1/', detOfePayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await detallesOfertaService.remove('d1');
    expect(del).toHaveBeenCalledWith('/compras/detalles-oferta-proveedor/d1/');
  });
});
