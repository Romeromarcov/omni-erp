import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

import { get, post } from '../services/api';
import { manufacturaService } from '../services/manufacturaService';

const orden = {
  id: 'of-1',
  producto: 'prod-1',
  cantidad: '10.00',
  fecha_inicio: '2026-06-01',
  fecha_fin: null,
  estado: 'pendiente',
  lista_materiales: 'bom-1',
  ruta_produccion: null,
  referencia_externa: 'OF-0001',
  observaciones: '',
};

const etapa = {
  id: 'et-1',
  orden_produccion: 'of-1',
  etapa: 'cat-1',
  etapa_codigo: 'corte',
  etapa_nombre: 'Corte',
  orden: 1,
  estado: 'pendiente' as const,
  horas_trabajadas: '0',
  tarifa_hora: '0',
  cantidad_destajo: '0',
  pago_destajo: '0',
  costo_mano_obra: '0',
  completada_por: null,
  fecha_completada: null,
  observaciones: '',
};

describe('manufacturaService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getOrdenesPaginated pasa page/page_size y devuelve la página DRF', async () => {
    vi.mocked(get).mockResolvedValue({ count: 1, next: null, previous: null, results: [orden] });
    const res = await manufacturaService.getOrdenesPaginated(2, 10);
    expect(get).toHaveBeenCalledWith('/manufactura/ordenes-produccion/?page=2&page_size=10');
    expect(res.count).toBe(1);
    expect(res.results[0].cantidad).toBe('10.00');
  });

  it('getOrdenesPaginated normaliza listas directas con toList', async () => {
    vi.mocked(get).mockResolvedValue([orden]);
    const res = await manufacturaService.getOrdenesPaginated();
    expect(res).toEqual({ count: 1, next: null, previous: null, results: [orden] });
  });

  it('getOrdenesPaginated tolera respuestas inesperadas', async () => {
    vi.mocked(get).mockResolvedValue(null);
    const res = await manufacturaService.getOrdenesPaginated();
    expect(res.results).toEqual([]);
    expect(res.count).toBe(0);
  });

  it('getOrden consulta el detalle por id', async () => {
    vi.mocked(get).mockResolvedValue(orden);
    const res = await manufacturaService.getOrden('of-1');
    expect(get).toHaveBeenCalledWith('/manufactura/ordenes-produccion/of-1/');
    expect(res.id).toBe('of-1');
  });

  it('getEtapas normaliza la lista de etapas', async () => {
    vi.mocked(get).mockResolvedValue([etapa]);
    const res = await manufacturaService.getEtapas('of-1');
    expect(get).toHaveBeenCalledWith('/manufactura/ordenes-produccion/of-1/etapas/');
    expect(res).toHaveLength(1);
    expect(res[0].etapa_codigo).toBe('corte');
  });

  it('avanzarEtapa envía horas/tarifa/destajo como strings decimales (R-CODE-4)', async () => {
    vi.mocked(post).mockResolvedValue({ estado_orden: 'en_proceso', etapa, etapas_pendientes: 5 });
    const res = await manufacturaService.avanzarEtapa('of-1', {
      horas_trabajadas: '2.5',
      tarifa_hora: '4.00',
      cantidad_destajo: '10',
      observaciones: 'ok',
    });
    expect(post).toHaveBeenCalledWith('/manufactura/ordenes-produccion/of-1/avanzar-etapa/', {
      horas_trabajadas: '2.5',
      tarifa_hora: '4.00',
      cantidad_destajo: '10',
      observaciones: 'ok',
    });
    expect(res.etapas_pendientes).toBe(5);
  });

  it('getCosteo devuelve el desglose con montos string', async () => {
    vi.mocked(get).mockResolvedValue({
      orden_id: 'of-1',
      estado: 'en_proceso',
      costo: {
        costo_materiales: '100.5000',
        mano_obra: '20.0000',
        costos_indirectos: '12.0500',
        costo_total: '132.5500',
        costo_unitario: '13.2550',
      },
      etapas: [etapa],
    });
    const res = await manufacturaService.getCosteo('of-1');
    expect(get).toHaveBeenCalledWith('/manufactura/ordenes-produccion/of-1/costeo/');
    expect(res.costo.costo_total).toBe('132.5500');
    expect(typeof res.costo.costo_unitario).toBe('string');
  });

  it('getMrp sin filtros no agrega querystring', async () => {
    vi.mocked(get).mockResolvedValue({ orden_id: 'of-1', cantidad: '10.00', faltantes: [] });
    await manufacturaService.getMrp('of-1');
    expect(get).toHaveBeenCalledWith('/manufactura/ordenes-produccion/of-1/mrp/');
  });

  it('getMrp pasa almacen_id e incluir_opcionales en la querystring', async () => {
    vi.mocked(get).mockResolvedValue({ orden_id: 'of-1', cantidad: '10.00', faltantes: [] });
    await manufacturaService.getMrp('of-1', { almacenId: 'alm-1', incluirOpcionales: true });
    expect(get).toHaveBeenCalledWith(
      '/manufactura/ordenes-produccion/of-1/mrp/?almacen_id=alm-1&incluir_opcionales=true',
    );
  });

  it('completarOrden envía almacen_id y cantidad opcional', async () => {
    vi.mocked(post).mockResolvedValue({
      estado: 'finalizada',
      produccion_id: 'pt-1',
      costo: {
        costo_materiales: '0',
        mano_obra: '0',
        costos_indirectos: '0',
        costo_total: '0',
        costo_unitario: '0',
      },
    });
    const res = await manufacturaService.completarOrden('of-1', { almacen_id: 'alm-1', cantidad: '10' });
    expect(post).toHaveBeenCalledWith('/manufactura/ordenes-produccion/of-1/completar/', {
      almacen_id: 'alm-1',
      cantidad: '10',
    });
    expect(res.estado).toBe('finalizada');
  });
});
