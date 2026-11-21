import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

import { get, post, patch } from '../services/api';
import { prediccionesService, type EjecucionAgente } from '../services/agentesService';

const prediccion = {
  id_prediccion: 'p1',
  esta_vigente: true,
  agente: 'clasificador_gastos',
  input_texto: 'Compra de papelería',
  input_monto: '120.00',
  input_metadata: {},
  categoria_predicha: 'oficina',
  confianza: 0.91,
  razonamiento: 'Texto coincide con útiles',
  alternativas: [],
  resultado_humano: 'pendiente',
  categoria_correcta: '',
  modelo_llm: 'fallback',
  latencia_ms: 12,
  fecha_prediccion: '2026-06-23T10:00:00Z',
  id_empresa: 'e1',
};

const makeEjecucion = <T = Record<string, unknown>>(
  overrides: Partial<EjecucionAgente<T>> = {},
): EjecucionAgente<T> => ({
  id_ejecucion: 'ej-1',
  agente: 'cobranza_estratega',
  estado: 'pendiente',
  celery_task_id: 'celery-1',
  parametros: {},
  resultado: {} as T,
  mensaje_error: '',
  iniciado_por: 'u1',
  fecha_creacion: '2026-11-21T00:00:00Z',
  fecha_inicio: null,
  fecha_fin: null,
  id_empresa: 'e1',
  ...overrides,
});

describe('prediccionesService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── getAll ────────────────────────────────────────────────────────────────
  it('getAll sin filtros pide la lista base y normaliza un array directo', async () => {
    vi.mocked(get).mockResolvedValue([prediccion]);
    const res = await prediccionesService.getAll();
    expect(get).toHaveBeenCalledWith('/agentes/predicciones/');
    expect(res).toHaveLength(1);
    expect(res[0].id_prediccion).toBe('p1');
  });

  it('getAll normaliza una respuesta paginada DRF', async () => {
    vi.mocked(get).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [prediccion],
    });
    const res = await prediccionesService.getAll();
    expect(res).toEqual([prediccion]);
  });

  it('getAll devuelve [] ante una respuesta inesperada', async () => {
    vi.mocked(get).mockResolvedValue({ foo: 'bar' });
    const res = await prediccionesService.getAll();
    expect(res).toEqual([]);
  });

  it('getAll arma el querystring con agente y resultado_humano', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await prediccionesService.getAll({
      agente: 'cobranza_estratega',
      resultado_humano: 'pendiente',
    });
    expect(get).toHaveBeenCalledWith(
      '/agentes/predicciones/?agente=cobranza_estratega&resultado_humano=pendiente',
    );
  });

  it('getAll solo con agente omite el resultado', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await prediccionesService.getAll({ agente: 'reorden_sugeridor' });
    expect(get).toHaveBeenCalledWith('/agentes/predicciones/?agente=reorden_sugeridor');
  });

  // ── getById ─────────────────────────────────────────────────────────────────
  it('getById consulta el detalle por id', async () => {
    vi.mocked(get).mockResolvedValue(prediccion);
    const res = await prediccionesService.getById('p1');
    expect(get).toHaveBeenCalledWith('/agentes/predicciones/p1/');
    expect(res.categoria_predicha).toBe('oficina');
  });

  // ── sugerenciasActivas ────────────────────────────────────────────────────
  it('sugerenciasActivas sin límite usa el endpoint base y devuelve sugerencias', async () => {
    vi.mocked(get).mockResolvedValue({ sugerencias: [{ id: 's1' }], total: 1 });
    const res = await prediccionesService.sugerenciasActivas();
    expect(get).toHaveBeenCalledWith('/agentes/predicciones/sugerencias-activas/');
    expect(res).toEqual([{ id: 's1' }]);
  });

  it('sugerenciasActivas con límite arma el querystring', async () => {
    vi.mocked(get).mockResolvedValue({ sugerencias: [], total: 0 });
    await prediccionesService.sugerenciasActivas(5);
    expect(get).toHaveBeenCalledWith('/agentes/predicciones/sugerencias-activas/?limite=5');
  });

  it('sugerenciasActivas devuelve [] si falta el campo sugerencias', async () => {
    vi.mocked(get).mockResolvedValue({ total: 0 });
    const res = await prediccionesService.sugerenciasActivas(10);
    expect(res).toEqual([]);
  });

  // ── responder ───────────────────────────────────────────────────────────────
  it('responder postea la acción sin comentario', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'p1', resultado_humano: 'aceptada' });
    const res = await prediccionesService.responder('p1', { accion: 'aceptar' });
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/p1/responder/', {
      accion: 'aceptar',
    });
    expect(res.resultado_humano).toBe('aceptada');
  });

  it('responder incluye el comentario cuando se provee', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'p1', resultado_humano: 'rechazada' });
    await prediccionesService.responder('p1', { accion: 'rechazar', comentario: 'No aplica' });
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/p1/responder/', {
      accion: 'rechazar',
      comentario: 'No aplica',
    });
  });

  // ── evaluar ─────────────────────────────────────────────────────────────────
  it('evaluar hace PATCH solo con el resultado', async () => {
    vi.mocked(patch).mockResolvedValue(prediccion);
    await prediccionesService.evaluar('p1', { resultado_humano: 'aceptada' });
    expect(patch).toHaveBeenCalledWith('/agentes/predicciones/p1/evaluar/', {
      resultado_humano: 'aceptada',
    });
  });

  it('evaluar incluye la categoría correcta cuando se provee', async () => {
    vi.mocked(patch).mockResolvedValue(prediccion);
    await prediccionesService.evaluar('p1', {
      resultado_humano: 'rechazada',
      categoria_correcta: 'transporte',
    });
    expect(patch).toHaveBeenCalledWith('/agentes/predicciones/p1/evaluar/', {
      resultado_humano: 'rechazada',
      categoria_correcta: 'transporte',
    });
  });

  // ── análisis asíncrono (HTTP 202 → EjecucionAgente) ───────────────────────
  it('analizarCobranza encola análisis y devuelve EjecucionAgente', async () => {
    const ej = makeEjecucion({ estado: 'pendiente' });
    vi.mocked(post).mockResolvedValue(ej);
    const res = await prediccionesService.analizarCobranza();
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/analizar-cobranza/', {});
    expect(res.id_ejecucion).toBe('ej-1');
    expect(res.estado).toBe('pendiente');
  });

  it('analizarReorden encola análisis con payload opcional', async () => {
    const ej = makeEjecucion({ agente: 'reorden_sugeridor' });
    vi.mocked(post).mockResolvedValue(ej);
    await prediccionesService.analizarReorden({ solo_alertas: false, persistir: true });
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/analizar-reorden/', {
      solo_alertas: false,
      persistir: true,
    });
  });

  it('analizarPersonalizacion encola análisis con body vacío', async () => {
    const ej = makeEjecucion({ agente: 'personalizacion_capa2' });
    vi.mocked(post).mockResolvedValue(ej);
    const res = await prediccionesService.analizarPersonalizacion();
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/analizar-personalizacion/', {});
    expect(res.agente).toBe('personalizacion_capa2');
  });

  // ── clasificarGasto ──────────────────────────────────────────────────────
  it('clasificarGasto sin aplicar omite el flag y retorna EjecucionAgente', async () => {
    const ej = makeEjecucion({ agente: 'clasificador_gastos' });
    vi.mocked(post).mockResolvedValue(ej);
    const res = await prediccionesService.clasificarGasto({ gasto_id: 'g1' });
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/clasificar-gasto/', {
      gasto_id: 'g1',
    });
    expect(res.id_ejecucion).toBe('ej-1');
  });

  it('clasificarGasto con aplicar=true envía el flag', async () => {
    vi.mocked(post).mockResolvedValue(makeEjecucion({ agente: 'clasificador_gastos' }));
    await prediccionesService.clasificarGasto({ gasto_id: 'g1', aplicar: true });
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/clasificar-gasto/', {
      gasto_id: 'g1',
      aplicar: true,
    });
  });

  it('clasificarGasto con aplicar=false envía el flag explícito', async () => {
    vi.mocked(post).mockResolvedValue(makeEjecucion({ agente: 'clasificador_gastos' }));
    await prediccionesService.clasificarGasto({ gasto_id: 'g1', aplicar: false });
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/clasificar-gasto/', {
      gasto_id: 'g1',
      aplicar: false,
    });
  });

  // ── ejecuciones y polling ─────────────────────────────────────────────────
  it('obtenerEjecucion consulta /agentes/ejecuciones/{id}/', async () => {
    const ej = makeEjecucion({ estado: 'completado', resultado: { total: 0 } });
    vi.mocked(get).mockResolvedValue(ej);
    const res = await prediccionesService.obtenerEjecucion('ej-1');
    expect(get).toHaveBeenCalledWith('/agentes/ejecuciones/ej-1/');
    expect(res.estado).toBe('completado');
  });

  it('obtenerEjecucion reenvía AbortSignal cuando se provee', async () => {
    const controller = new AbortController();
    const ej = makeEjecucion({ estado: 'ejecutando' });
    vi.mocked(get).mockResolvedValue(ej);
    await prediccionesService.obtenerEjecucion('ej-1', controller.signal);
    expect(get).toHaveBeenCalledWith('/agentes/ejecuciones/ej-1/', { signal: controller.signal });
  });

  it('listarEjecuciones arma querystring con agente y estado', async () => {
    vi.mocked(get).mockResolvedValue({ results: [makeEjecucion()] });
    const res = await prediccionesService.listarEjecuciones({
      agente: 'cobranza_estratega',
      estado: 'completado',
    });
    expect(get).toHaveBeenCalledWith(
      '/agentes/ejecuciones/?agente=cobranza_estratega&estado=completado',
    );
    expect(res).toHaveLength(1);
  });

  it('esperarEjecucion hace polling hasta completado y reporta estados', async () => {
    const inicial = makeEjecucion({ estado: 'pendiente' });
    const ejecutando = makeEjecucion({ estado: 'ejecutando' });
    const completado = makeEjecucion({ estado: 'completado', resultado: { total: 2 } });
    vi.mocked(get).mockResolvedValueOnce(ejecutando).mockResolvedValueOnce(completado);

    const estados: string[] = [];
    const finalEj = await prediccionesService.esperarEjecucion(inicial, {
      intervalMs: 1,
      maxIntentos: 5,
      onEstado: (e) => estados.push(e.estado),
    });

    expect(finalEj.estado).toBe('completado');
    expect(estados).toEqual(['pendiente', 'ejecutando', 'completado']);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('esperarEjecucion retorna inmediatamente si ya está fallido', async () => {
    const fallido = makeEjecucion({ estado: 'fallido', mensaje_error: 'Error controlado.' });
    const res = await prediccionesService.esperarEjecucion(fallido, { intervalMs: 1 });
    expect(res.estado).toBe('fallido');
    expect(get).not.toHaveBeenCalled();
  });

  it('esperarEjecucion respeta AbortSignal cancelando el polling', async () => {
    const controller = new AbortController();
    const inicial = makeEjecucion({ estado: 'pendiente' });
    const promesa = prediccionesService.esperarEjecucion(inicial, {
      intervalMs: 5000,
      maxIntentos: 5,
      signal: controller.signal,
    });
    controller.abort();
    await expect(promesa).rejects.toThrow();
    expect(get).not.toHaveBeenCalled();
  });

  it('esperarEjecucion lanza timeout cuando excede maxIntentos', async () => {
    const pendiente = makeEjecucion({ estado: 'pendiente' });
    vi.mocked(get).mockResolvedValue(pendiente);
    await expect(
      prediccionesService.esperarEjecucion(pendiente, { intervalMs: 1, maxIntentos: 2 }),
    ).rejects.toThrow(/Tiempo de espera agotado/);
  });

  // ── metricasClasificador ────────────────────────────────────────────────
  it('metricasClasificador consulta el action y devuelve las métricas', async () => {
    const metricas = {
      total: 150,
      evaluadas: 80,
      precision: 0.923,
      confianza_promedio: 0.847,
      latencia_promedio_ms: 12,
    };
    vi.mocked(get).mockResolvedValue(metricas);
    const res = await prediccionesService.metricasClasificador();
    expect(get).toHaveBeenCalledWith('/agentes/predicciones/metricas-clasificador/');
    expect(res.precision).toBe(0.923);
  });

  // ── propagación de errores ──────────────────────────────────────────────
  it('propaga el error del cliente HTTP', async () => {
    vi.mocked(get).mockRejectedValue(new Error('boom'));
    await expect(prediccionesService.getAll()).rejects.toThrow('boom');
  });
});
