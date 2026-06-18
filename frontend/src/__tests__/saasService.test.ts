import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  fetchText: vi.fn(),
}));

import { get, post, patch, fetchText } from '../services/api';
import {
  estimarMrr,
  fetchPlan,
  fetchPlanes,
  createPlan,
  updatePlan,
  fetchSuscripcion,
  fetchSuscripciones,
  createSuscripcion,
  updateSuscripcion,
  activarSuscripcion,
  suspenderSuscripcion,
  deactivatePlan,
  cancelarSuscripcion,
  signup,
  type Plan,
  type Suscripcion,
} from '../services/saasService';

function plan(p: Partial<Plan>): Plan {
  return {
    id_plan: 'p1',
    nombre: 'Pro',
    nivel: 'PRO',
    descripcion: '',
    precio_mensual: '30.00',
    precio_anual: '300.00',
    max_usuarios: 10,
    max_empresas: 1,
    max_documentos_mes: 1000,
    permite_ia: true,
    permite_api: true,
    permite_reportes_avanzados: false,
    permite_multimoneda: false,
    soporte: 'email',
    activo: true,
    fecha_creacion: '',
    fecha_actualizacion: '',
    ...p,
  };
}

function sus(s: Partial<Suscripcion>): Suscripcion {
  return {
    id_suscripcion: 's1',
    id_empresa: 'e1',
    id_plan: 'p1',
    estado: 'ACTIVA',
    periodo: 'MENSUAL',
    fecha_inicio: '2026-01-01',
    fecha_fin: '2026-12-31',
    fecha_cancelacion: null,
    fecha_suspension: null,
    renovacion_automatica: true,
    monto_pagado: '0',
    referencia_pago: '',
    notas: '',
    fecha_creacion: '',
    fecha_actualizacion: '',
    esta_vigente: true,
    dias_restantes: 100,
    plan_nombre: 'Pro',
    plan_nivel: 'PRO',
    ...s,
  };
}

describe('estimarMrr', () => {
  const planes = [
    plan({ id_plan: 'p1', precio_mensual: '30.00', precio_anual: '300.00' }),
    plan({ id_plan: 'p2', precio_mensual: '50.00', precio_anual: '600.00' }),
  ];

  it('suma el precio mensual de suscripciones mensuales vigentes', () => {
    const subs = [sus({ id_plan: 'p1', periodo: 'MENSUAL', estado: 'ACTIVA' })];
    expect(estimarMrr(subs, planes)).toBeCloseTo(30);
  });

  it('mensualiza el precio anual dividiendo entre 12', () => {
    const subs = [sus({ id_plan: 'p2', periodo: 'ANUAL', estado: 'ACTIVA' })];
    expect(estimarMrr(subs, planes)).toBeCloseTo(600 / 12);
  });

  it('cuenta TRIAL como vigente pero ignora CANCELADA/SUSPENDIDA/VENCIDA', () => {
    const subs = [
      sus({ id_suscripcion: 'a', id_plan: 'p1', estado: 'TRIAL' }),
      sus({ id_suscripcion: 'b', id_plan: 'p1', estado: 'CANCELADA' }),
      sus({ id_suscripcion: 'c', id_plan: 'p1', estado: 'SUSPENDIDA' }),
      sus({ id_suscripcion: 'd', id_plan: 'p1', estado: 'VENCIDA' }),
    ];
    expect(estimarMrr(subs, planes)).toBeCloseTo(30);
  });

  it('ignora suscripciones cuyo plan no existe en el catálogo', () => {
    const subs = [sus({ id_plan: 'desconocido', estado: 'ACTIVA' })];
    expect(estimarMrr(subs, planes)).toBe(0);
  });
});

describe('saasService — llamadas API', () => {
  beforeEach(() => vi.clearAllMocks());

  it('fetchPlanes sin inactivos no añade query param', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await fetchPlanes(false);
    expect(get).toHaveBeenCalledWith('/saas/planes/');
  });

  it('fetchPlanes con inactivos añade incluir_inactivos=true', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await fetchPlanes(true);
    expect(get).toHaveBeenCalledWith('/saas/planes/?incluir_inactivos=true');
  });

  it('fetchPlanes desempaqueta respuestas paginadas', async () => {
    vi.mocked(get).mockResolvedValue({ results: [plan({ id_plan: 'x' })], count: 1 });
    const res = await fetchPlanes(false);
    expect(res).toHaveLength(1);
    expect(res[0].id_plan).toBe('x');
  });

  it('fetchSuscripciones aplica filtro de estado', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await fetchSuscripciones({ estado: 'ACTIVA' });
    expect(get).toHaveBeenCalledWith('/saas/suscripciones/?estado=ACTIVA');
  });

  it('deactivatePlan usa DELETE vía fetchText (tolera 204 sin body)', async () => {
    vi.mocked(fetchText).mockResolvedValue('');
    await deactivatePlan('p1');
    expect(fetchText).toHaveBeenCalledWith('/saas/planes/p1/', { method: 'DELETE' });
  });

  it('cancelarSuscripcion envía las notas en el body', async () => {
    vi.mocked(post).mockResolvedValue(sus({}));
    await cancelarSuscripcion('s1', 'impago');
    expect(post).toHaveBeenCalledWith('/saas/suscripciones/s1/cancelar/', { notas: 'impago' });
  });

  it('signup hace POST al endpoint público con el payload', async () => {
    vi.mocked(post).mockResolvedValue({
      empresa_id: 'e1', usuario_id: 'u1', username: 'admin', suscripcion_id: 's1',
      plan: 'Free', estado: 'TRIAL', trial_fin: '2026-07-07',
    });
    const payload = {
      empresa_nombre_legal: 'Prospecto SA',
      username: 'admin',
      email: 'a@b.com',
      password: 'ContraseñaSegura123',
    };
    const res = await signup(payload);
    expect(post).toHaveBeenCalledWith('/saas/signup/', payload);
    expect(res.estado).toBe('TRIAL');
  });

  it('fetchPlan / createPlan / updatePlan pegan al endpoint correcto', async () => {
    vi.mocked(get).mockResolvedValue(plan({ id_plan: 'p1' }));
    await fetchPlan('p1');
    expect(get).toHaveBeenCalledWith('/saas/planes/p1/');

    vi.mocked(post).mockResolvedValue(plan({}));
    await createPlan({ nombre: 'Pro' } as never);
    expect(post).toHaveBeenCalledWith('/saas/planes/', { nombre: 'Pro' });

    vi.mocked(patch).mockResolvedValue(plan({}));
    await updatePlan('p1', { nombre: 'X' });
    expect(patch).toHaveBeenCalledWith('/saas/planes/p1/', { nombre: 'X' });
  });

  it('fetchSuscripciones sin filtro no añade query; con empresa lo incluye', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await fetchSuscripciones();
    expect(get).toHaveBeenCalledWith('/saas/suscripciones/');

    await fetchSuscripciones({ empresa: 'e9' });
    expect(get).toHaveBeenCalledWith('/saas/suscripciones/?empresa=e9');
  });

  it('fetchSuscripcion / createSuscripcion / updateSuscripcion', async () => {
    vi.mocked(get).mockResolvedValue(sus({ id_suscripcion: 's1' }));
    await fetchSuscripcion('s1');
    expect(get).toHaveBeenCalledWith('/saas/suscripciones/s1/');

    vi.mocked(post).mockResolvedValue(sus({}));
    await createSuscripcion({ id_empresa: 'e1', id_plan: 'p1' } as never);
    expect(post).toHaveBeenCalledWith('/saas/suscripciones/', { id_empresa: 'e1', id_plan: 'p1' });

    vi.mocked(patch).mockResolvedValue(sus({}));
    await updateSuscripcion('s1', { notas: 'al día' });
    expect(patch).toHaveBeenCalledWith('/saas/suscripciones/s1/', { notas: 'al día' });
  });

  it('activarSuscripcion hace PATCH estado=ACTIVA; suspender pega a su acción', async () => {
    vi.mocked(patch).mockResolvedValue(sus({}));
    await activarSuscripcion('s1');
    expect(patch).toHaveBeenCalledWith('/saas/suscripciones/s1/', { estado: 'ACTIVA' });

    vi.mocked(post).mockResolvedValue(sus({}));
    await suspenderSuscripcion('s1');
    expect(post).toHaveBeenCalledWith('/saas/suscripciones/s1/suspender/', {});
  });

  it('cancelarSuscripcion sin notas usa string vacío por defecto', async () => {
    vi.mocked(post).mockResolvedValue(sus({}));
    await cancelarSuscripcion('s1');
    expect(post).toHaveBeenCalledWith('/saas/suscripciones/s1/cancelar/', { notas: '' });
  });
});
