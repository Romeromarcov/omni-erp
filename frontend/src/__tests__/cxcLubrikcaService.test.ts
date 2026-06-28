import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, put, patch, del } from '../services/api';
import { cxcLubrikcaService } from '../services/cxcLubrikcaService';

const B = '/cxc-lubrikca';

describe('cxcLubrikcaService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── CRUD genérico por entidad de configuración ─────────────────────────────
  // Tabla de recursos: cada entrada prueba list/create/update/patch/remove.
  const recursos: {
    nombre: string;
    recurso: string;
    list: () => Promise<unknown>;
    create: (d: Record<string, unknown>) => Promise<unknown>;
    update: (id: number, d: Record<string, unknown>) => Promise<unknown>;
    patch: (id: number, d: Record<string, unknown>) => Promise<unknown>;
    remove: (id: number) => Promise<unknown>;
  }[] = [
    {
      nombre: 'descuentos-marca',
      recurso: 'descuentos-marca-categoria',
      list: cxcLubrikcaService.listDescuentosMarca,
      create: cxcLubrikcaService.crearDescuentoMarca,
      update: cxcLubrikcaService.actualizarDescuentoMarca,
      patch: cxcLubrikcaService.patchDescuentoMarca,
      remove: cxcLubrikcaService.eliminarDescuentoMarca,
    },
    {
      nombre: 'descuentos-bcv',
      recurso: 'descuentos-bcv-completo',
      list: cxcLubrikcaService.listDescuentosBcv,
      create: cxcLubrikcaService.crearDescuentoBcv,
      update: cxcLubrikcaService.actualizarDescuentoBcv,
      patch: cxcLubrikcaService.patchDescuentoBcv,
      remove: cxcLubrikcaService.eliminarDescuentoBcv,
    },
    {
      nombre: 'promociones',
      recurso: 'promociones-primera-compra',
      list: cxcLubrikcaService.listPromociones,
      create: cxcLubrikcaService.crearPromocion,
      update: cxcLubrikcaService.actualizarPromocion,
      patch: cxcLubrikcaService.patchPromocion,
      remove: cxcLubrikcaService.eliminarPromocion,
    },
    {
      nombre: 'recurrencia',
      recurso: 'reglas-recurrencia',
      list: cxcLubrikcaService.listReglasRecurrencia,
      create: cxcLubrikcaService.crearReglaRecurrencia,
      update: cxcLubrikcaService.actualizarReglaRecurrencia,
      patch: cxcLubrikcaService.patchReglaRecurrencia,
      remove: cxcLubrikcaService.eliminarReglaRecurrencia,
    },
    {
      nombre: 'feriados',
      recurso: 'feriados',
      list: cxcLubrikcaService.listFeriados,
      create: cxcLubrikcaService.crearFeriado,
      update: cxcLubrikcaService.actualizarFeriado,
      patch: cxcLubrikcaService.patchFeriado,
      remove: cxcLubrikcaService.eliminarFeriado,
    },
    {
      nombre: 'metodos-pago',
      recurso: 'metodos-pago',
      list: cxcLubrikcaService.listMetodosPago,
      create: cxcLubrikcaService.crearMetodoPago,
      update: cxcLubrikcaService.actualizarMetodoPago,
      patch: cxcLubrikcaService.patchMetodoPago,
      remove: cxcLubrikcaService.eliminarMetodoPago,
    },
    {
      nombre: 'config-conciliacion',
      recurso: 'config-conciliacion',
      list: cxcLubrikcaService.listConfigConciliacion,
      create: cxcLubrikcaService.crearConfigConciliacion,
      update: cxcLubrikcaService.actualizarConfigConciliacion,
      patch: cxcLubrikcaService.patchConfigConciliacion,
      remove: cxcLubrikcaService.eliminarConfigConciliacion,
    },
  ];

  recursos.forEach((r) => {
    describe(`CRUD ${r.nombre}`, () => {
      it('list normaliza la respuesta paginada DRF', async () => {
        vi.mocked(get).mockResolvedValue({ count: 1, results: [{ id: 1 }] });
        const res = await r.list();
        expect(get).toHaveBeenCalledWith(`${B}/${r.recurso}/`);
        expect(res).toEqual([{ id: 1 }]);
      });

      it('list normaliza listas directas', async () => {
        vi.mocked(get).mockResolvedValue([{ id: 2 }]);
        const res = await r.list();
        expect(res).toEqual([{ id: 2 }]);
      });

      it('create hace POST con payload', async () => {
        vi.mocked(post).mockResolvedValue({ id: 9 });
        const res = await r.create({ activo: true });
        expect(post).toHaveBeenCalledWith(`${B}/${r.recurso}/`, { activo: true });
        expect(res).toEqual({ id: 9 });
      });

      it('update hace PUT por id', async () => {
        vi.mocked(put).mockResolvedValue({ id: 3 });
        await r.update(3, { activo: false });
        expect(put).toHaveBeenCalledWith(`${B}/${r.recurso}/3/`, { activo: false });
      });

      it('patch hace PATCH por id', async () => {
        vi.mocked(patch).mockResolvedValue({ id: 3 });
        await r.patch(3, { activo: false });
        expect(patch).toHaveBeenCalledWith(`${B}/${r.recurso}/3/`, { activo: false });
      });

      it('remove hace DELETE por id', async () => {
        vi.mocked(del).mockResolvedValue(undefined);
        await r.remove(7);
        expect(del).toHaveBeenCalledWith(`${B}/${r.recurso}/7/`);
      });
    });
  });

  // ── Operación: lecturas ────────────────────────────────────────────────────
  it('listPedidos normaliza la respuesta', async () => {
    vi.mocked(get).mockResolvedValue({ results: [{ id: 'p1' }] });
    const res = await cxcLubrikcaService.listPedidos();
    expect(get).toHaveBeenCalledWith(`${B}/pedidos/`);
    expect(res).toEqual([{ id: 'p1' }]);
  });

  it('listLineasPedido consulta el endpoint', async () => {
    vi.mocked(get).mockResolvedValue([{ id: 'l1' }]);
    await cxcLubrikcaService.listLineasPedido();
    expect(get).toHaveBeenCalledWith(`${B}/lineas-pedido/`);
  });

  it('listPreciosLista consulta el endpoint', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await cxcLubrikcaService.listPreciosLista();
    expect(get).toHaveBeenCalledWith(`${B}/precios-lista/`);
  });

  it('listPagos consulta el endpoint', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await cxcLubrikcaService.listPagos();
    expect(get).toHaveBeenCalledWith(`${B}/pagos/`);
  });

  it('listVinculaciones consulta el endpoint', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await cxcLubrikcaService.listVinculaciones();
    expect(get).toHaveBeenCalledWith(`${B}/vinculaciones/`);
  });

  it('listBandeja consulta el endpoint', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await cxcLubrikcaService.listBandeja();
    expect(get).toHaveBeenCalledWith(`${B}/bandeja/`);
  });

  it('listConciliaciones consulta el endpoint', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await cxcLubrikcaService.listConciliaciones();
    expect(get).toHaveBeenCalledWith(`${B}/conciliaciones/`);
  });

  // ── Operación: acciones POST ───────────────────────────────────────────────
  it('recalcularPedido hace POST a la acción del pedido', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'b1' });
    await cxcLubrikcaService.recalcularPedido('p1');
    expect(post).toHaveBeenCalledWith(`${B}/pedidos/p1/recalcular/`, {});
  });

  it('sincronizarPedidos sin desde envía body vacío', async () => {
    vi.mocked(post).mockResolvedValue({ pedidos: 3 });
    const res = await cxcLubrikcaService.sincronizarPedidos();
    expect(post).toHaveBeenCalledWith(`${B}/pedidos/sincronizar/`, {});
    expect(res).toEqual({ pedidos: 3 });
  });

  it('sincronizarPedidos con desde lo incluye en el body', async () => {
    vi.mocked(post).mockResolvedValue({});
    await cxcLubrikcaService.sincronizarPedidos('2026-06-01');
    expect(post).toHaveBeenCalledWith(`${B}/pedidos/sincronizar/`, { desde: '2026-06-01' });
  });

  it('registrarVinculacion hace POST con el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'v1' });
    const payload = {
      pedido: 'p1',
      pago: 'pg1',
      monto_aplicado: '100.00',
      hora_pago_confirmada: '2026-06-01T10:00:00Z',
    };
    await cxcLubrikcaService.registrarVinculacion(payload);
    expect(post).toHaveBeenCalledWith(`${B}/vinculaciones/registrar/`, payload);
  });

  it('proponerCierre hace POST a la acción de la bandeja', async () => {
    vi.mocked(post).mockResolvedValue({ solicitud: 's1' });
    await cxcLubrikcaService.proponerCierre('b1');
    expect(post).toHaveBeenCalledWith(`${B}/bandeja/b1/proponer/`, {});
  });

  it('confirmarCierre hace POST con el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'b1' });
    await cxcLubrikcaService.confirmarCierre('b1', { aprobado: true, comentarios: 'ok' });
    expect(post).toHaveBeenCalledWith(`${B}/bandeja/b1/confirmar/`, {
      aprobado: true,
      comentarios: 'ok',
    });
  });

  it('conciliar hace POST con el pedido', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'c1' });
    await cxcLubrikcaService.conciliar({ pedido: 'p1' });
    expect(post).toHaveBeenCalledWith(`${B}/conciliaciones/conciliar/`, { pedido: 'p1' });
  });

  it('revisarConciliacion hace POST a la acción', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'c1' });
    await cxcLubrikcaService.revisarConciliacion('c1');
    expect(post).toHaveBeenCalledWith(`${B}/conciliaciones/c1/revisar/`, {});
  });

  it('getResumen consulta el resumen de cartera', async () => {
    const resumen = {
      por_resultado: { verde: 1, amarillo: 2, rojo: 3 },
      total_conciliados: 6,
      total_facturados: 10,
      facturados_sin_conciliar: 4,
      pedidos_con_devolucion: 1,
      cartera_atascada: 2,
      bandejas_candidatas_sin_aprobar: 0,
      diferencia_total: '12.34',
    };
    vi.mocked(get).mockResolvedValue(resumen);
    const res = await cxcLubrikcaService.getResumen();
    expect(get).toHaveBeenCalledWith(`${B}/conciliaciones/resumen/`);
    expect(res).toEqual(resumen);
  });
});
