import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  fetchBlob: vi.fn(),
  API_URL: 'http://localhost:8000/api',
}));

import { get, post, fetchBlob } from '../services/api';
import {
  despachoService,
  detalleDespachoService,
  puedeTransicionar,
  TRANSICIONES_DESPACHO,
  type DespachoDesdeNotaVentaPayload,
} from '../services/despachoService';

const payloadDesdeNota: DespachoDesdeNotaVentaPayload = {
  id_nota_venta: 'nv1',
  almacen_id: 'a1',
  direccion_entrega: 'Av. Principal',
  observaciones: 'Entregar de mañana',
};

describe('puedeTransicionar / TRANSICIONES_DESPACHO', () => {
  it('PENDIENTE permite EN_RUTA y CANCELADO', () => {
    expect(puedeTransicionar('PENDIENTE', 'EN_RUTA')).toBe(true);
    expect(puedeTransicionar('PENDIENTE', 'CANCELADO')).toBe(true);
    expect(puedeTransicionar('PENDIENTE', 'ENTREGADO')).toBe(false);
    expect(puedeTransicionar('PENDIENTE', 'DEVUELTO')).toBe(false);
  });

  it('EN_RUTA permite ENTREGADO y DEVUELTO', () => {
    expect(puedeTransicionar('EN_RUTA', 'ENTREGADO')).toBe(true);
    expect(puedeTransicionar('EN_RUTA', 'DEVUELTO')).toBe(true);
    expect(puedeTransicionar('EN_RUTA', 'CANCELADO')).toBe(false);
  });

  it('los estados terminales no permiten ninguna transición', () => {
    expect(TRANSICIONES_DESPACHO.ENTREGADO).toEqual([]);
    expect(TRANSICIONES_DESPACHO.DEVUELTO).toEqual([]);
    expect(TRANSICIONES_DESPACHO.CANCELADO).toEqual([]);
    for (const terminal of ['ENTREGADO', 'DEVUELTO', 'CANCELADO'] as const) {
      expect(puedeTransicionar(terminal, 'EN_RUTA')).toBe(false);
      expect(puedeTransicionar(terminal, 'ENTREGADO')).toBe(false);
    }
  });

  it('un estado desconocido devuelve false (rama de fallback)', () => {
    expect(puedeTransicionar('OTRO' as never, 'EN_RUTA')).toBe(false);
  });
});

describe('despachoService.getAll', () => {
  beforeEach(() => vi.clearAllMocks());

  it('arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_despacho: 'd1' }] });
    const r = await despachoService.getAll({
      empresa: 'e1',
      estado: 'PENDIENTE',
      transportista: '7',
      notaVenta: 'nv1',
    });
    expect(get).toHaveBeenCalledWith(
      '/despacho/despachos/?empresa=e1&estado=PENDIENTE&id_transportista=7&id_nota_venta=nv1',
    );
    expect(r).toEqual([{ id_despacho: 'd1' }]);
  });

  it('sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await despachoService.getAll();
    expect(get).toHaveBeenCalledWith('/despacho/despachos/');
  });

  it('con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await despachoService.getAll({});
    expect(get).toHaveBeenCalledWith('/despacho/despachos/');
  });

  it('solo con estado', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await despachoService.getAll({ estado: 'EN_RUTA' });
    expect(get).toHaveBeenCalledWith('/despacho/despachos/?estado=EN_RUTA');
  });

  it('solo con transportista', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await despachoService.getAll({ transportista: '3' });
    expect(get).toHaveBeenCalledWith('/despacho/despachos/?id_transportista=3');
  });

  it('solo con notaVenta', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await despachoService.getAll({ notaVenta: 'nv9' });
    expect(get).toHaveBeenCalledWith('/despacho/despachos/?id_nota_venta=nv9');
  });

  it('normaliza un array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_despacho: 'd1' }, { id_despacho: 'd2' }]);
    expect((await despachoService.getAll()).length).toBe(2);
  });

  it('ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await despachoService.getAll()).toEqual([]);
  });
});

describe('despachoService acciones', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_despacho: 'd1' });
    await despachoService.getById('d1');
    expect(get).toHaveBeenCalledWith('/despacho/despachos/d1/');
  });

  it('desdeNotaVenta postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_despacho: 'd1' });
    await despachoService.desdeNotaVenta(payloadDesdeNota);
    expect(post).toHaveBeenCalledWith('/despacho/despachos/desde-nota-venta/', payloadDesdeNota);
  });

  it('desdeNotaVenta propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('cupo excedido'));
    await expect(despachoService.desdeNotaVenta(payloadDesdeNota)).rejects.toThrow('cupo');
  });

  it('iniciarRuta sin transportista manda cuerpo vacío', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_despacho: 'd1', estado_despacho: 'EN_RUTA' });
    await despachoService.iniciarRuta('d1');
    expect(post).toHaveBeenCalledWith('/despacho/despachos/d1/iniciar-ruta/', {});
  });

  it('iniciarRuta con transportista lo incluye', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_despacho: 'd1' });
    await despachoService.iniciarRuta('d1', 42);
    expect(post).toHaveBeenCalledWith('/despacho/despachos/d1/iniciar-ruta/', {
      id_transportista: 42,
    });
  });

  it('iniciarRuta con transportista null manda cuerpo vacío (rama falsy)', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_despacho: 'd1' });
    await despachoService.iniciarRuta('d1', null);
    expect(post).toHaveBeenCalledWith('/despacho/despachos/d1/iniciar-ruta/', {});
  });

  it('entregar con solo receptor envía únicamente receptor', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_despacho: 'd1', estado_despacho: 'ENTREGADO' });
    await despachoService.entregar('d1', { receptor: 'Juan' });
    expect(post).toHaveBeenCalledWith('/despacho/despachos/d1/entregar/', { receptor: 'Juan' });
  });

  it('entregar con documento y firma incluye ambos', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_despacho: 'd1' });
    await despachoService.entregar('d1', {
      receptor: 'Juan',
      documento_receptor: 'V-123',
      firma_base64: 'data:img',
    });
    expect(post).toHaveBeenCalledWith('/despacho/despachos/d1/entregar/', {
      receptor: 'Juan',
      documento_receptor: 'V-123',
      firma_base64: 'data:img',
    });
  });

  it('entregar omite documento/firma cuando vienen vacíos (ramas falsy)', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_despacho: 'd1' });
    await despachoService.entregar('d1', {
      receptor: 'Ana',
      documento_receptor: '',
      firma_base64: '',
    });
    expect(post).toHaveBeenCalledWith('/despacho/despachos/d1/entregar/', { receptor: 'Ana' });
  });

  it('devolver postea el motivo', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_despacho: 'd1', estado_despacho: 'DEVUELTO' });
    await despachoService.devolver('d1', 'cliente ausente');
    expect(post).toHaveBeenCalledWith('/despacho/despachos/d1/devolver/', {
      motivo: 'cliente ausente',
    });
  });

  it('cancelar postea el motivo', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_despacho: 'd1', estado_despacho: 'CANCELADO' });
    await despachoService.cancelar('d1', 'duplicado');
    expect(post).toHaveBeenCalledWith('/despacho/despachos/d1/cancelar/', { motivo: 'duplicado' });
  });

  it('cancelar propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('transición inválida'));
    await expect(despachoService.cancelar('d1', 'x')).rejects.toThrow('transición');
  });

  it('pdfUrl arma la URL absoluta', () => {
    expect(despachoService.pdfUrl('d1')).toBe('http://localhost:8000/api/despacho/despachos/d1/pdf/');
  });
});

describe('despachoService.descargarPdf', () => {
  beforeEach(() => vi.clearAllMocks());

  it('descarga el PDF con nombre por número de despacho', async () => {
    const blob = new Blob(['%PDF'], { type: 'application/pdf' });
    vi.mocked(fetchBlob).mockResolvedValueOnce(blob);
    const createObjUrl = vi.fn(() => 'blob:url');
    const revokeObjUrl = vi.fn();
    globalThis.URL.createObjectURL = createObjUrl as unknown as typeof URL.createObjectURL;
    globalThis.URL.revokeObjectURL = revokeObjUrl as unknown as typeof URL.revokeObjectURL;
    const click = vi.fn();
    const anchor = { href: '', download: '', click } as unknown as HTMLAnchorElement;
    const createEl = vi.spyOn(document, 'createElement').mockReturnValueOnce(anchor);
    const append = vi.spyOn(document.body, 'appendChild').mockImplementationOnce((n) => n);
    const remove = vi.spyOn(document.body, 'removeChild').mockImplementationOnce((n) => n);

    await despachoService.descargarPdf('d1', 'DESP-001');

    expect(fetchBlob).toHaveBeenCalledWith('/despacho/despachos/d1/pdf/', {
      headers: { Accept: 'application/pdf' },
    });
    expect(anchor.download).toBe('nota_entrega_DESP-001.pdf');
    expect(click).toHaveBeenCalled();
    expect(revokeObjUrl).toHaveBeenCalledWith('blob:url');

    createEl.mockRestore();
    append.mockRestore();
    remove.mockRestore();
  });

  it('usa el id como nombre cuando no se pasa número (rama fallback)', async () => {
    const blob = new Blob(['%PDF'], { type: 'application/pdf' });
    vi.mocked(fetchBlob).mockResolvedValueOnce(blob);
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:url') as unknown as typeof URL.createObjectURL;
    globalThis.URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL;
    const anchor = { href: '', download: '', click: vi.fn() } as unknown as HTMLAnchorElement;
    const createEl = vi.spyOn(document, 'createElement').mockReturnValueOnce(anchor);
    const append = vi.spyOn(document.body, 'appendChild').mockImplementationOnce((n) => n);
    const remove = vi.spyOn(document.body, 'removeChild').mockImplementationOnce((n) => n);

    await despachoService.descargarPdf('d1');
    expect(anchor.download).toBe('nota_entrega_d1.pdf');

    createEl.mockRestore();
    append.mockRestore();
    remove.mockRestore();
  });

  it('propaga el error si la descarga falla', async () => {
    vi.mocked(fetchBlob).mockRejectedValueOnce(new Error('503'));
    await expect(despachoService.descargarPdf('d1')).rejects.toThrow('503');
  });
});

describe('detalleDespachoService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll filtra por despacho en el cliente y codifica el id', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_detalle_despacho: 'l1', id_despacho: 'd1' },
      { id_detalle_despacho: 'l2', id_despacho: 'otro' },
    ]);
    const r = await detalleDespachoService.getAll({ despacho: 'd1' });
    expect(get).toHaveBeenCalledWith('/despacho/detalles-despacho/?id_despacho=d1');
    expect(r.map((d) => d.id_detalle_despacho)).toEqual(['l1']);
  });

  it('getAll filtra sobre respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [
        { id_detalle_despacho: 'l1', id_despacho: 'd1' },
        { id_detalle_despacho: 'l2', id_despacho: 'otro' },
      ],
    });
    const r = await detalleDespachoService.getAll({ despacho: 'd1' });
    expect(r.map((d) => d.id_detalle_despacho)).toEqual(['l1']);
  });

  it('getAll sin despacho devuelve la lista completa', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_detalle_despacho: 'l1', id_despacho: 'd1' }]);
    const r = await detalleDespachoService.getAll();
    expect(get).toHaveBeenCalledWith('/despacho/detalles-despacho/');
    expect(r.length).toBe(1);
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as never);
    expect(await detalleDespachoService.getAll()).toEqual([]);
  });
});
