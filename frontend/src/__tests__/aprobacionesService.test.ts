import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  tiposAprobacionService,
  flujosAprobacionService,
  solicitudesAprobacionService,
  registrosAprobacionService,
  solicitudEstaCerrada,
  type TipoAprobacionPayload,
  type FlujoAprobacionPayload,
  type SolicitudAprobacionPayload,
  type RegistroAprobacionPayload,
} from '../services/aprobacionesService';

const tipoPayload: TipoAprobacionPayload = {
  id_empresa: 'e1',
  codigo_tipo: 'COMPRA',
  nombre_tipo: 'Aprobación de compra',
  descripcion: 'desc',
  modulo_origen: 'compras',
  activo: true,
};

const flujoPayload: FlujoAprobacionPayload = {
  id_tipo_aprobacion: 't1',
  orden_etapa: 1,
  nombre_etapa: 'Jefatura',
  rol_aprobador: 'r1',
  id_usuario_aprobador: null,
  monto_minimo: '0.00',
  monto_maximo: '1000.00',
  activo: true,
};

const solicitudPayload: SolicitudAprobacionPayload = {
  id_tipo_aprobacion: 't1',
  id_entidad_origen: 'oc-1',
  nombre_modelo_origen: 'OrdenCompra',
  id_usuario_solicitante: 'u1',
  estado_solicitud: 'PENDIENTE',
  comentarios_solicitante: null,
  etapa_actual_flujo: null,
};

const registroPayload: RegistroAprobacionPayload = {
  id_solicitud_aprobacion: 's1',
  id_flujo_aprobacion_etapa: 'f1',
  id_usuario_aprobador: 'u2',
  tipo_decision: 'APROBADO',
  comentarios: 'ok',
};

describe('solicitudEstaCerrada', () => {
  it('es true para estados terminales', () => {
    expect(solicitudEstaCerrada('APROBADA')).toBe(true);
    expect(solicitudEstaCerrada('RECHAZADA')).toBe(true);
    expect(solicitudEstaCerrada('CANCELADA')).toBe(true);
  });
  it('es false para estados activos', () => {
    expect(solicitudEstaCerrada('PENDIENTE')).toBe(false);
    expect(solicitudEstaCerrada('EN_PROCESO')).toBe(false);
    expect(solicitudEstaCerrada('')).toBe(false);
  });
});

describe('tiposAprobacionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con empresa y modulo', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_tipo_aprobacion: 't1' }] });
    const r = await tiposAprobacionService.getAll({ empresa: 'e1', modulo: 'compras' });
    expect(get).toHaveBeenCalledWith(
      '/gestion-aprobaciones/tipos-aprobacion/?id_empresa=e1&modulo_origen=compras',
    );
    expect(r).toEqual([{ id_tipo_aprobacion: 't1' }]);
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_tipo_aprobacion: 't1' }]);
    await tiposAprobacionService.getAll();
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/tipos-aprobacion/');
  });

  it('getAll con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await tiposAprobacionService.getAll({});
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/tipos-aprobacion/');
  });

  it('getAll solo con empresa', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await tiposAprobacionService.getAll({ empresa: 'e1' });
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/tipos-aprobacion/?id_empresa=e1');
  });

  it('getAll solo con modulo', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await tiposAprobacionService.getAll({ modulo: 'gastos' });
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/tipos-aprobacion/?modulo_origen=gastos');
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await tiposAprobacionService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_tipo_aprobacion: 't1' });
    await tiposAprobacionService.getById('t1');
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/tipos-aprobacion/t1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_tipo_aprobacion: 't1' });
    await tiposAprobacionService.create(tipoPayload);
    expect(post).toHaveBeenCalledWith('/gestion-aprobaciones/tipos-aprobacion/', tipoPayload);

    vi.mocked(patch).mockResolvedValue({ id_tipo_aprobacion: 't1' });
    await tiposAprobacionService.update('t1', tipoPayload);
    expect(patch).toHaveBeenCalledWith('/gestion-aprobaciones/tipos-aprobacion/t1/', tipoPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await tiposAprobacionService.remove('t1');
    expect(del).toHaveBeenCalledWith('/gestion-aprobaciones/tipos-aprobacion/t1/');
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('boom'));
    await expect(tiposAprobacionService.create(tipoPayload)).rejects.toThrow('boom');
  });
});

describe('flujosAprobacionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con tipo', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_flujo_aprobacion: 'f1' }] });
    const r = await flujosAprobacionService.getAll({ tipo: 't1' });
    expect(get).toHaveBeenCalledWith(
      '/gestion-aprobaciones/flujos-aprobacion/?id_tipo_aprobacion=t1',
    );
    expect(r).toEqual([{ id_flujo_aprobacion: 'f1' }]);
  });

  it('getAll sin parámetros', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await flujosAprobacionService.getAll();
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/flujos-aprobacion/');
  });

  it('getAll con objeto vacío', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await flujosAprobacionService.getAll({});
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/flujos-aprobacion/');
  });

  it('getAll normaliza array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_flujo_aprobacion: 'f1' }]);
    expect((await flujosAprobacionService.getAll()).length).toBe(1);
  });

  it('getById', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_flujo_aprobacion: 'f1' });
    await flujosAprobacionService.getById('f1');
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/flujos-aprobacion/f1/');
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_flujo_aprobacion: 'f1' });
    await flujosAprobacionService.create(flujoPayload);
    expect(post).toHaveBeenCalledWith('/gestion-aprobaciones/flujos-aprobacion/', flujoPayload);

    vi.mocked(patch).mockResolvedValue({ id_flujo_aprobacion: 'f1' });
    await flujosAprobacionService.update('f1', flujoPayload);
    expect(patch).toHaveBeenCalledWith('/gestion-aprobaciones/flujos-aprobacion/f1/', flujoPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await flujosAprobacionService.remove('f1');
    expect(del).toHaveBeenCalledWith('/gestion-aprobaciones/flujos-aprobacion/f1/');
  });

  it('update propaga el error del backend', async () => {
    vi.mocked(patch).mockRejectedValueOnce(new Error('conflicto'));
    await expect(flujosAprobacionService.update('f1', flujoPayload)).rejects.toThrow('conflicto');
  });
});

describe('solicitudesAprobacionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con tipo y estado', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_solicitud_aprobacion: 's1' }] });
    const r = await solicitudesAprobacionService.getAll({ tipo: 't1', estado: 'PENDIENTE' });
    expect(get).toHaveBeenCalledWith(
      '/gestion-aprobaciones/solicitudes-aprobacion/?id_tipo_aprobacion=t1&estado_solicitud=PENDIENTE',
    );
    expect(r).toEqual([{ id_solicitud_aprobacion: 's1' }]);
  });

  it('getAll sin parámetros', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await solicitudesAprobacionService.getAll();
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/solicitudes-aprobacion/');
  });

  it('getAll con objeto vacío', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await solicitudesAprobacionService.getAll({});
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/solicitudes-aprobacion/');
  });

  it('getAll solo con estado', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await solicitudesAprobacionService.getAll({ estado: 'APROBADA' });
    expect(get).toHaveBeenCalledWith(
      '/gestion-aprobaciones/solicitudes-aprobacion/?estado_solicitud=APROBADA',
    );
  });

  it('getAll solo con tipo', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await solicitudesAprobacionService.getAll({ tipo: 't1' });
    expect(get).toHaveBeenCalledWith(
      '/gestion-aprobaciones/solicitudes-aprobacion/?id_tipo_aprobacion=t1',
    );
  });

  it('getById', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_solicitud_aprobacion: 's1' });
    await solicitudesAprobacionService.getById('s1');
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/solicitudes-aprobacion/s1/');
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_solicitud_aprobacion: 's1' });
    await solicitudesAprobacionService.create(solicitudPayload);
    expect(post).toHaveBeenCalledWith(
      '/gestion-aprobaciones/solicitudes-aprobacion/',
      solicitudPayload,
    );

    vi.mocked(patch).mockResolvedValue({ id_solicitud_aprobacion: 's1' });
    await solicitudesAprobacionService.update('s1', solicitudPayload);
    expect(patch).toHaveBeenCalledWith(
      '/gestion-aprobaciones/solicitudes-aprobacion/s1/',
      solicitudPayload,
    );

    vi.mocked(del).mockResolvedValue(undefined);
    await solicitudesAprobacionService.remove('s1');
    expect(del).toHaveBeenCalledWith('/gestion-aprobaciones/solicitudes-aprobacion/s1/');
  });

  it('cambiarEstado hace PATCH parcial del estado', async () => {
    vi.mocked(patch).mockResolvedValue({ id_solicitud_aprobacion: 's1', estado_solicitud: 'APROBADA' });
    await solicitudesAprobacionService.cambiarEstado('s1', 'APROBADA');
    expect(patch).toHaveBeenCalledWith('/gestion-aprobaciones/solicitudes-aprobacion/s1/', {
      estado_solicitud: 'APROBADA',
    });
  });

  it('remove propaga el error del backend', async () => {
    vi.mocked(del).mockRejectedValueOnce(new Error('no encontrado'));
    await expect(solicitudesAprobacionService.remove('s1')).rejects.toThrow('no encontrado');
  });
});

describe('registrosAprobacionService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll con solicitud filtra y arma el querystring', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [
        { id_registro_aprobacion: 'r1', id_solicitud_aprobacion: 's1' },
        { id_registro_aprobacion: 'r2', id_solicitud_aprobacion: 's2' },
      ],
    });
    const r = await registrosAprobacionService.getAll({ solicitud: 's1' });
    expect(get).toHaveBeenCalledWith(
      '/gestion-aprobaciones/registros-aprobacion/?id_solicitud_aprobacion=s1',
    );
    expect(r).toEqual([{ id_registro_aprobacion: 'r1', id_solicitud_aprobacion: 's1' }]);
  });

  it('getAll sin parámetros no filtra', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_registro_aprobacion: 'r1', id_solicitud_aprobacion: 's1' },
      { id_registro_aprobacion: 'r2', id_solicitud_aprobacion: 's2' },
    ]);
    const r = await registrosAprobacionService.getAll();
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/registros-aprobacion/');
    expect(r.length).toBe(2);
  });

  it('getAll con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await registrosAprobacionService.getAll({});
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/registros-aprobacion/');
  });

  it('getById', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_registro_aprobacion: 'r1' });
    await registrosAprobacionService.getById('r1');
    expect(get).toHaveBeenCalledWith('/gestion-aprobaciones/registros-aprobacion/r1/');
  });

  it('create / update / remove', async () => {
    vi.mocked(post).mockResolvedValue({ id_registro_aprobacion: 'r1' });
    await registrosAprobacionService.create(registroPayload);
    expect(post).toHaveBeenCalledWith('/gestion-aprobaciones/registros-aprobacion/', registroPayload);

    vi.mocked(patch).mockResolvedValue({ id_registro_aprobacion: 'r1' });
    await registrosAprobacionService.update('r1', registroPayload);
    expect(patch).toHaveBeenCalledWith(
      '/gestion-aprobaciones/registros-aprobacion/r1/',
      registroPayload,
    );

    vi.mocked(del).mockResolvedValue(undefined);
    await registrosAprobacionService.remove('r1');
    expect(del).toHaveBeenCalledWith('/gestion-aprobaciones/registros-aprobacion/r1/');
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('falló'));
    await expect(registrosAprobacionService.create(registroPayload)).rejects.toThrow('falló');
  });
});
