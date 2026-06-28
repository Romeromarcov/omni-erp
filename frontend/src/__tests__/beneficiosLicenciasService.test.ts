import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  beneficiosService,
  beneficiosEmpleadoService,
  tiposLicenciaService,
  licenciasEmpleadoService,
  type BeneficioPayload,
  type BeneficioEmpleadoPayload,
  type TipoLicenciaPayload,
  type LicenciaEmpleadoPayload,
} from '../services/beneficiosLicenciasService';

const beneficioPayload: BeneficioPayload = {
  id_empresa: 'e1',
  nombre_beneficio: 'Bono de alimentación',
  descripcion: null,
  tipo_beneficio: 'ALIMENTACION',
  monto_fijo: '100.0000',
  porcentaje_salario: null,
  es_obligatorio: false,
  activo: true,
};

const asignacionPayload: BeneficioEmpleadoPayload = {
  id_empleado: 7,
  id_beneficio: 'b1',
  fecha_inicio: '2026-06-01',
  fecha_fin: null,
  monto_personalizado: '120.0000',
  porcentaje_personalizado: null,
  estado: 'ACTIVO',
  observaciones: null,
};

const tipoPayload: TipoLicenciaPayload = {
  id_empresa: 'e1',
  nombre_tipo: 'Vacaciones',
  descripcion: null,
  es_remunerada: true,
  dias_maximos_por_año: 15,
  requiere_aprobacion: true,
  activo: true,
};

const licenciaPayload: LicenciaEmpleadoPayload = {
  id_empleado: 7,
  id_tipo_licencia: 't1',
  fecha_inicio: '2026-06-01',
  fecha_fin: '2026-06-05',
  dias_solicitados: 5,
  motivo: 'Asuntos personales',
  estado: 'PENDIENTE',
};

describe('beneficiosService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza la rama paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_beneficio: 'b1' }] });
    const r = await beneficiosService.getAll();
    expect(get).toHaveBeenCalledWith('/rrhh/beneficios/');
    expect(r).toEqual([{ id_beneficio: 'b1' }]);
  });

  it('getAll normaliza la rama array', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_beneficio: 'b1' }]);
    const r = await beneficiosService.getAll();
    expect(r).toHaveLength(1);
  });

  it('getAll normaliza una respuesta vacía/no reconocida', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    const r = await beneficiosService.getAll();
    expect(r).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_beneficio: 'b1' });
    await beneficiosService.getById('b1');
    expect(get).toHaveBeenCalledWith('/rrhh/beneficios/b1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_beneficio: 'b2' });
    await beneficiosService.create(beneficioPayload);
    expect(post).toHaveBeenCalledWith('/rrhh/beneficios/', beneficioPayload);

    vi.mocked(patch).mockResolvedValue({ id_beneficio: 'b1' });
    await beneficiosService.update('b1', beneficioPayload);
    expect(patch).toHaveBeenCalledWith('/rrhh/beneficios/b1/', beneficioPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await beneficiosService.remove('b1');
    expect(del).toHaveBeenCalledWith('/rrhh/beneficios/b1/');
  });

  it('propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ detail: 'Falló' })));
    await expect(beneficiosService.create(beneficioPayload)).rejects.toThrow();
  });
});

describe('beneficiosEmpleadoService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll filtra por empleado en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_beneficio_empleado: 'a1', id_empleado: 7 },
      { id_beneficio_empleado: 'a2', id_empleado: 9 },
    ]);
    const r = await beneficiosEmpleadoService.getAll({ empleado: 7 });
    expect(get).toHaveBeenCalledWith('/rrhh/beneficios-empleado/');
    expect(r.map((a) => a.id_beneficio_empleado)).toEqual(['a1']);
  });

  it('getAll sin filtro devuelve todo (rama paginada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [{ id_beneficio_empleado: 'a1', id_empleado: 7 }],
    });
    const r = await beneficiosEmpleadoService.getAll();
    expect(r).toHaveLength(1);
  });

  it('getAll con empleado vacío no filtra (rama array vacía)', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    const r = await beneficiosEmpleadoService.getAll({ empleado: '' });
    expect(r).toEqual([]);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_beneficio_empleado: 'a1' });
    await beneficiosEmpleadoService.create(asignacionPayload);
    expect(post).toHaveBeenCalledWith('/rrhh/beneficios-empleado/', asignacionPayload);

    vi.mocked(patch).mockResolvedValue({ id_beneficio_empleado: 'a1' });
    await beneficiosEmpleadoService.update('a1', asignacionPayload);
    expect(patch).toHaveBeenCalledWith('/rrhh/beneficios-empleado/a1/', asignacionPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await beneficiosEmpleadoService.remove('a1');
    expect(del).toHaveBeenCalledWith('/rrhh/beneficios-empleado/a1/');
  });
});

describe('tiposLicenciaService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza la rama array', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_tipo_licencia: 't1' }]);
    const r = await tiposLicenciaService.getAll();
    expect(get).toHaveBeenCalledWith('/rrhh/tipos-licencia/');
    expect(r).toHaveLength(1);
  });

  it('getAll normaliza rama paginada y respuesta vacía', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_tipo_licencia: 't1' }] });
    expect(await tiposLicenciaService.getAll()).toHaveLength(1);
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    expect(await tiposLicenciaService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_tipo_licencia: 't1' });
    await tiposLicenciaService.getById('t1');
    expect(get).toHaveBeenCalledWith('/rrhh/tipos-licencia/t1/');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_tipo_licencia: 't2' });
    await tiposLicenciaService.create(tipoPayload);
    expect(post).toHaveBeenCalledWith('/rrhh/tipos-licencia/', tipoPayload);

    vi.mocked(patch).mockResolvedValue({ id_tipo_licencia: 't1' });
    await tiposLicenciaService.update('t1', tipoPayload);
    expect(patch).toHaveBeenCalledWith('/rrhh/tipos-licencia/t1/', tipoPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await tiposLicenciaService.remove('t1');
    expect(del).toHaveBeenCalledWith('/rrhh/tipos-licencia/t1/');
  });
});

describe('licenciasEmpleadoService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll filtra por empleado y estado en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_licencia: 'l1', id_empleado: 7, estado: 'PENDIENTE' },
      { id_licencia: 'l2', id_empleado: 7, estado: 'APROBADA' },
      { id_licencia: 'l3', id_empleado: 9, estado: 'PENDIENTE' },
    ]);
    const r = await licenciasEmpleadoService.getAll({ empleado: 7, estado: 'PENDIENTE' });
    expect(get).toHaveBeenCalledWith('/rrhh/licencias-empleado/');
    expect(r.map((l) => l.id_licencia)).toEqual(['l1']);
  });

  it('getAll sin filtros devuelve todo (rama paginada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [{ id_licencia: 'l1', id_empleado: 7, estado: 'PENDIENTE' }],
    });
    const r = await licenciasEmpleadoService.getAll();
    expect(r).toHaveLength(1);
  });

  it('getAll con respuesta vacía/no reconocida', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    const r = await licenciasEmpleadoService.getAll({ estado: 'APROBADA' });
    expect(r).toEqual([]);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_licencia: 'l2' });
    await licenciasEmpleadoService.create(licenciaPayload);
    expect(post).toHaveBeenCalledWith('/rrhh/licencias-empleado/', licenciaPayload);

    vi.mocked(patch).mockResolvedValue({ id_licencia: 'l1' });
    await licenciasEmpleadoService.update('l1', licenciaPayload);
    expect(patch).toHaveBeenCalledWith('/rrhh/licencias-empleado/l1/', licenciaPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await licenciasEmpleadoService.remove('l1');
    expect(del).toHaveBeenCalledWith('/rrhh/licencias-empleado/l1/');
  });

  it('cambiarEstado hace PATCH parcial sobre estado (aprobar/rechazar)', async () => {
    vi.mocked(patch).mockResolvedValue({ id_licencia: 'l1', estado: 'APROBADA' });
    await licenciasEmpleadoService.cambiarEstado('l1', { estado: 'APROBADA' });
    expect(patch).toHaveBeenCalledWith('/rrhh/licencias-empleado/l1/', { estado: 'APROBADA' });

    await licenciasEmpleadoService.cambiarEstado('l1', {
      estado: 'RECHAZADA',
      observaciones_aprobacion: 'No procede',
    });
    expect(patch).toHaveBeenCalledWith('/rrhh/licencias-empleado/l1/', {
      estado: 'RECHAZADA',
      observaciones_aprobacion: 'No procede',
    });
  });
});
