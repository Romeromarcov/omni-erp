import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  listasMaterialesService,
  listasMaterialesDetalleService,
  rutasProduccionService,
  rutasProduccionDetalleService,
  centrosTrabajoService,
  operacionesProduccionService,
  type ListaMaterialesPayload,
  type ListaMaterialesDetallePayload,
  type RutaProduccionPayload,
  type RutaProduccionDetallePayload,
  type CentroTrabajoPayload,
  type OperacionProduccionPayload,
} from '../services/manufacturaMaestrosService';

const bomPayload: ListaMaterialesPayload = {
  producto_final: 'p1',
  nombre: 'Mesa BOM',
  descripcion: 'desc',
  referencia_externa: 'V1',
};

const componentePayload: ListaMaterialesDetallePayload = {
  id_lista_materiales: 'b1',
  id_producto: 'p2',
  cantidad_requerida: '4.0000',
  id_unidad_medida: 'u1',
  es_opcional: false,
  observaciones: '',
};

const rutaPayload: RutaProduccionPayload = {
  nombre: 'Ruta mesa',
  descripcion: 'desc',
  referencia_externa: 'R1',
};

const pasoPayload: RutaProduccionDetallePayload = {
  id_ruta_produccion: 'r1',
  id_operacion: 'op1',
  id_centro_trabajo: 'c1',
  numero_secuencia: 1,
  tiempo_preparacion_minutos: '5.00',
  tiempo_operacion_minutos: '30.00',
  observaciones: '',
};

const centroPayload: CentroTrabajoPayload = {
  codigo_centro: 'CT-1',
  nombre_centro: 'Corte',
  descripcion: '',
  tipo_centro: 'MAQUINA',
  capacidad_horas_dia: '8.00',
  costo_hora: '12.0000',
  activo: true,
};

const operacionPayload: OperacionProduccionPayload = {
  codigo_operacion: 'OP-1',
  nombre_operacion: 'Cortar',
  descripcion: '',
  tiempo_estandar_minutos: '15.00',
  activo: true,
};

describe('listasMaterialesService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza la rama paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id: 'b1' }] });
    const r = await listasMaterialesService.getAll();
    expect(get).toHaveBeenCalledWith('/manufactura/listas-materiales/');
    expect(r).toEqual([{ id: 'b1' }]);
  });

  it('getAll normaliza la rama array', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id: 'b1' }]);
    const r = await listasMaterialesService.getAll();
    expect(r).toEqual([{ id: 'b1' }]);
  });

  it('getAll normaliza respuesta vacía/no reconocida', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    expect(await listasMaterialesService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id: 'b1' });
    await listasMaterialesService.getById('b1');
    expect(get).toHaveBeenCalledWith('/manufactura/listas-materiales/b1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'b2' });
    await listasMaterialesService.create(bomPayload);
    expect(post).toHaveBeenCalledWith('/manufactura/listas-materiales/', bomPayload);

    vi.mocked(patch).mockResolvedValue({ id: 'b1' });
    await listasMaterialesService.update('b1', bomPayload);
    expect(patch).toHaveBeenCalledWith('/manufactura/listas-materiales/b1/', bomPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await listasMaterialesService.remove('b1');
    expect(del).toHaveBeenCalledWith('/manufactura/listas-materiales/b1/');
  });
});

describe('listasMaterialesDetalleService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll filtra por BOM en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_detalle_lista: 'd1', id_lista_materiales: 'b1' },
      { id_detalle_lista: 'd2', id_lista_materiales: 'otra' },
    ]);
    const r = await listasMaterialesDetalleService.getAll({ lista: 'b1' });
    expect(get).toHaveBeenCalledWith('/manufactura/listas-materiales-detalle/');
    expect(r.map((d) => d.id_detalle_lista)).toEqual(['d1']);
  });

  it('getAll sin lista no filtra (rama paginada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_detalle_lista: 'd1', id_lista_materiales: 'b1' }] });
    const r = await listasMaterialesDetalleService.getAll();
    expect(r).toHaveLength(1);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_lista: 'd1' });
    await listasMaterialesDetalleService.create(componentePayload);
    expect(post).toHaveBeenCalledWith('/manufactura/listas-materiales-detalle/', componentePayload);

    vi.mocked(patch).mockResolvedValue({ id_detalle_lista: 'd1' });
    await listasMaterialesDetalleService.update('d1', componentePayload);
    expect(patch).toHaveBeenCalledWith('/manufactura/listas-materiales-detalle/d1/', componentePayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await listasMaterialesDetalleService.remove('d1');
    expect(del).toHaveBeenCalledWith('/manufactura/listas-materiales-detalle/d1/');
  });
});

describe('rutasProduccionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza array y getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id: 'r1' }]);
    expect(await rutasProduccionService.getAll()).toEqual([{ id: 'r1' }]);
    expect(get).toHaveBeenCalledWith('/manufactura/rutas-produccion/');

    vi.mocked(get).mockResolvedValueOnce({ id: 'r1' });
    await rutasProduccionService.getById('r1');
    expect(get).toHaveBeenCalledWith('/manufactura/rutas-produccion/r1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'r2' });
    await rutasProduccionService.create(rutaPayload);
    expect(post).toHaveBeenCalledWith('/manufactura/rutas-produccion/', rutaPayload);

    vi.mocked(patch).mockResolvedValue({ id: 'r1' });
    await rutasProduccionService.update('r1', rutaPayload);
    expect(patch).toHaveBeenCalledWith('/manufactura/rutas-produccion/r1/', rutaPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await rutasProduccionService.remove('r1');
    expect(del).toHaveBeenCalledWith('/manufactura/rutas-produccion/r1/');
  });
});

describe('rutasProduccionDetalleService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll filtra por ruta en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_detalle_ruta: 'd1', id_ruta_produccion: 'r1' },
      { id_detalle_ruta: 'd2', id_ruta_produccion: 'otra' },
    ]);
    const r = await rutasProduccionDetalleService.getAll({ ruta: 'r1' });
    expect(get).toHaveBeenCalledWith('/manufactura/rutas-produccion-detalle/');
    expect(r.map((d) => d.id_detalle_ruta)).toEqual(['d1']);
  });

  it('getAll sin ruta no filtra (rama vacía)', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    expect(await rutasProduccionDetalleService.getAll()).toEqual([]);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_detalle_ruta: 'd1' });
    await rutasProduccionDetalleService.create(pasoPayload);
    expect(post).toHaveBeenCalledWith('/manufactura/rutas-produccion-detalle/', pasoPayload);

    vi.mocked(patch).mockResolvedValue({ id_detalle_ruta: 'd1' });
    await rutasProduccionDetalleService.update('d1', pasoPayload);
    expect(patch).toHaveBeenCalledWith('/manufactura/rutas-produccion-detalle/d1/', pasoPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await rutasProduccionDetalleService.remove('d1');
    expect(del).toHaveBeenCalledWith('/manufactura/rutas-produccion-detalle/d1/');
  });
});

describe('centrosTrabajoService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza y getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_centro_trabajo: 'c1' }] });
    expect(await centrosTrabajoService.getAll()).toEqual([{ id_centro_trabajo: 'c1' }]);
    expect(get).toHaveBeenCalledWith('/manufactura/centros-trabajo/');

    vi.mocked(get).mockResolvedValueOnce({ id_centro_trabajo: 'c1' });
    await centrosTrabajoService.getById('c1');
    expect(get).toHaveBeenCalledWith('/manufactura/centros-trabajo/c1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_centro_trabajo: 'c2' });
    await centrosTrabajoService.create(centroPayload);
    expect(post).toHaveBeenCalledWith('/manufactura/centros-trabajo/', centroPayload);

    vi.mocked(patch).mockResolvedValue({ id_centro_trabajo: 'c1' });
    await centrosTrabajoService.update('c1', centroPayload);
    expect(patch).toHaveBeenCalledWith('/manufactura/centros-trabajo/c1/', centroPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await centrosTrabajoService.remove('c1');
    expect(del).toHaveBeenCalledWith('/manufactura/centros-trabajo/c1/');
  });
});

describe('operacionesProduccionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza array', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_operacion: 'op1' }]);
    expect(await operacionesProduccionService.getAll()).toEqual([{ id_operacion: 'op1' }]);
    expect(get).toHaveBeenCalledWith('/manufactura/operaciones-produccion/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_operacion: 'op2' });
    await operacionesProduccionService.create(operacionPayload);
    expect(post).toHaveBeenCalledWith('/manufactura/operaciones-produccion/', operacionPayload);

    vi.mocked(patch).mockResolvedValue({ id_operacion: 'op1' });
    await operacionesProduccionService.update('op1', operacionPayload);
    expect(patch).toHaveBeenCalledWith('/manufactura/operaciones-produccion/op1/', operacionPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await operacionesProduccionService.remove('op1');
    expect(del).toHaveBeenCalledWith('/manufactura/operaciones-produccion/op1/');
  });
});
