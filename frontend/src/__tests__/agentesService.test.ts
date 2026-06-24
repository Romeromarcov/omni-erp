import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

import { get, post, patch } from '../services/api';
import { prediccionesService } from '../services/agentesService';

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

  // ── análisis ──────────────────────────────────────────────────────────────
  it('analizarCobranza postea al action con body vacío', async () => {
    vi.mocked(post).mockResolvedValue({ sugerencias: [], total: 0 });
    const res = await prediccionesService.analizarCobranza();
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/analizar-cobranza/', {});
    expect(res.total).toBe(0);
  });

  it('analizarReorden postea al action con body vacío', async () => {
    vi.mocked(post).mockResolvedValue({ sugerencias: [], total: 0 });
    await prediccionesService.analizarReorden();
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/analizar-reorden/', {});
  });

  it('analizarPersonalizacion postea al action con body vacío', async () => {
    vi.mocked(post).mockResolvedValue({
      flujo_documentos: {},
      listas_precios: {},
      credito_clientes: {},
    });
    const res = await prediccionesService.analizarPersonalizacion();
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/analizar-personalizacion/', {});
    expect(res).toHaveProperty('flujo_documentos');
  });

  // ── clasificarGasto ──────────────────────────────────────────────────────
  it('clasificarGasto sin aplicar omite el flag', async () => {
    vi.mocked(post).mockResolvedValue({ categoria: 'oficina', aplicado: false });
    await prediccionesService.clasificarGasto({ gasto_id: 'g1' });
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/clasificar-gasto/', {
      gasto_id: 'g1',
    });
  });

  it('clasificarGasto con aplicar=true envía el flag', async () => {
    vi.mocked(post).mockResolvedValue({ categoria: 'oficina', aplicado: true });
    const res = await prediccionesService.clasificarGasto({ gasto_id: 'g1', aplicar: true });
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/clasificar-gasto/', {
      gasto_id: 'g1',
      aplicar: true,
    });
    expect(res.aplicado).toBe(true);
  });

  it('clasificarGasto con aplicar=false envía el flag explícito', async () => {
    vi.mocked(post).mockResolvedValue({ categoria: 'oficina', aplicado: false });
    await prediccionesService.clasificarGasto({ gasto_id: 'g1', aplicar: false });
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/clasificar-gasto/', {
      gasto_id: 'g1',
      aplicar: false,
    });
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
