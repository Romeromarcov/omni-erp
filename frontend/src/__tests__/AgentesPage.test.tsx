import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

import { get, post, patch } from '../services/api';
import AgentesPage from '../pages/Agentes/AgentesPage';

const prediccionPendiente = {
  id_prediccion: 'p1',
  esta_vigente: true,
  agente: 'clasificador_gastos',
  input_texto: 'Compra de papelería',
  input_monto: '120.00',
  input_metadata: {},
  categoria_predicha: 'oficina',
  confianza: 0.91,
  razonamiento: 'Coincide con útiles',
  alternativas: [],
  resultado_humano: 'pendiente',
  categoria_correcta: '',
  modelo_llm: 'fallback',
  latencia_ms: 12,
  fecha_prediccion: '2026-06-23T10:00:00Z',
  id_empresa: 'e1',
};

const prediccionAceptada = {
  ...prediccionPendiente,
  id_prediccion: 'p2',
  agente: 'cobranza_estratega',
  categoria_predicha: 'contactar',
  resultado_humano: 'aceptada',
  esta_vigente: false,
};

const metricas = {
  total: 150,
  evaluadas: 80,
  precision: 0.923,
  confianza_promedio: 0.847,
  latencia_promedio_ms: 12,
};

const ejecucionBase = {
  id_ejecucion: 'ej-1',
  agente: 'cobranza_estratega',
  estado: 'pendiente' as const,
  celery_task_id: 'celery-1',
  parametros: {},
  resultado: {},
  mensaje_error: '',
  iniciado_por: 'u1',
  fecha_creacion: '2026-11-21T00:00:00Z',
  fecha_inicio: null,
  fecha_fin: null,
  id_empresa: 'e1',
};

const resumenConsumoDefault = {
  llamadas: 3,
  tokens_entrada_total: 1500,
  tokens_salida_total: 600,
  costo_total_usd: '0.013500',
  latencia_promedio_ms: 245,
  por_modelo: [
    {
      modelo: 'modelo-sonnet-test',
      llamadas: 2,
      tokens_entrada_total: 1000,
      tokens_salida_total: 400,
      costo_total_usd: '0.009000',
    },
    {
      modelo: 'modelo-haiku-test',
      llamadas: 1,
      tokens_entrada_total: 500,
      tokens_salida_total: 200,
      costo_total_usd: '0.004500',
    },
  ],
  por_uso: [
    {
      uso: 'chat',
      llamadas: 2,
      tokens_entrada_total: 1000,
      tokens_salida_total: 400,
      costo_total_usd: '0.009000',
    },
    {
      uso: 'agente',
      llamadas: 1,
      tokens_entrada_total: 500,
      tokens_salida_total: 200,
      costo_total_usd: '0.004500',
    },
  ],
};

function setupGet(predicciones = [prediccionPendiente, prediccionAceptada]) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/agentes/consumo-llm/resumen'))
      return Promise.resolve(resumenConsumoDefault);
    if (url.startsWith('/agentes/predicciones/metricas-clasificador'))
      return Promise.resolve(metricas);
    if (url.startsWith('/agentes/predicciones')) return Promise.resolve(predicciones);
    return Promise.resolve([]);
  });
}

function renderPage(pollIntervalMs = 5) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AgentesPage pollIntervalMs={pollIntervalMs} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AgentesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista las predicciones con agente, predicción y resultado', async () => {
    renderPage();
    expect(await screen.findByText('oficina')).toBeInTheDocument();
    expect(screen.getAllByText('Clasificador de Gastos').length).toBeGreaterThan(0);
    expect(screen.getByText('Pendiente')).toBeInTheDocument();
    expect(screen.getByText('Aceptada')).toBeInTheDocument();
    expect(screen.getAllByText('91%').length).toBeGreaterThan(0);
  });

  it('muestra las métricas del clasificador', async () => {
    renderPage();
    expect(await screen.findByText('150')).toBeInTheDocument(); // total
    expect(screen.getByText('92%')).toBeInTheDocument(); // precisión redondeada
    expect(screen.getByText('12 ms')).toBeInTheDocument();
  });

  it('filtra por agente y arma el querystring', async () => {
    renderPage();
    await screen.findByText('oficina');
    fireEvent.mouseDown(screen.getByLabelText('Agente'));
    fireEvent.click(await screen.findByRole('option', { name: 'Estratega de Cobranza' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/agentes/predicciones/?agente=cobranza_estratega'),
    );
  });

  it('filtra por resultado y arma el querystring', async () => {
    renderPage();
    await screen.findByText('oficina');
    fireEvent.mouseDown(screen.getByLabelText('Resultado'));
    fireEvent.click(await screen.findByRole('option', { name: 'Pendiente' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/agentes/predicciones/?resultado_humano=pendiente'),
    );
  });

  it('responde (aceptar) una predicción pendiente', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'p1', resultado_humano: 'aceptada' });
    renderPage();
    await screen.findByText('oficina');
    const fila = screen.getByText('oficina').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Aceptar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/agentes/predicciones/p1/responder/', {
        accion: 'aceptar',
      }),
    );
  });

  it('re-evalúa una predicción ya respondida vía PATCH', async () => {
    vi.mocked(patch).mockResolvedValue(prediccionAceptada);
    renderPage();
    await screen.findByText('contactar');
    const fila = screen.getByText('contactar').closest('tr')!;
    // Ya aceptada → el botón ofrece marcarla Rechazada.
    fireEvent.click(within(fila).getByRole('button', { name: /Rechazada/ }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/agentes/predicciones/p2/evaluar/', {
        resultado_humano: 'rechazada',
      }),
    );
  });

  it('dispara análisis de cobranza (202), hace polling y muestra el resultado completado', async () => {
    vi.mocked(post).mockResolvedValue({ ...ejecucionBase, estado: 'pendiente' });
    let pollCount = 0;
    vi.mocked(get).mockImplementation((url: string) => {
      if (url === '/agentes/ejecuciones/ej-1/') {
        pollCount += 1;
        if (pollCount === 1) {
          return Promise.resolve({ ...ejecucionBase, estado: 'ejecutando' });
        }
        return Promise.resolve({
          ...ejecucionBase,
          estado: 'completado',
          resultado: { sugerencias: [], total: 0 },
        });
      }
      if (url.startsWith('/agentes/predicciones/metricas-clasificador'))
        return Promise.resolve(metricas);
      if (url.startsWith('/agentes/predicciones'))
        return Promise.resolve([prediccionPendiente, prediccionAceptada]);
      return Promise.resolve([]);
    });

    renderPage(5);
    await screen.findByText('oficina');
    fireEvent.click(screen.getByRole('button', { name: 'Analizar cobranza' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/agentes/predicciones/analizar-cobranza/', {}),
    );
    expect(await screen.findByText(/Análisis de cobranza/)).toBeInTheDocument();
    expect(screen.getByText('Completado')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/agentes/ejecuciones/ej-1/', {
      signal: expect.any(AbortSignal),
    });
  });

  it('muestra error limpio cuando la ejecución termina en estado fallido', async () => {
    vi.mocked(post).mockResolvedValue({ ...ejecucionBase, estado: 'pendiente' });
    vi.mocked(get).mockImplementation((url: string) => {
      if (url === '/agentes/ejecuciones/ej-1/') {
        return Promise.resolve({
          ...ejecucionBase,
          estado: 'fallido',
          mensaje_error: 'No se pudo completar el análisis del agente.',
        });
      }
      if (url.startsWith('/agentes/predicciones/metricas-clasificador'))
        return Promise.resolve(metricas);
      if (url.startsWith('/agentes/predicciones'))
        return Promise.resolve([prediccionPendiente, prediccionAceptada]);
      return Promise.resolve([]);
    });

    renderPage(5);
    await screen.findByText('oficina');
    fireEvent.click(screen.getByRole('button', { name: 'Analizar cobranza' }));

    expect(
      await screen.findByText('No se pudo completar el análisis del agente.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Fallido')).toBeInTheDocument();
  });

  it('cancela el polling limpiamente al desmontar sin llamadas posteriores', async () => {
    vi.mocked(post).mockResolvedValue({ ...ejecucionBase, estado: 'pendiente' });
    const { unmount } = renderPage(500);
    await screen.findByText('oficina');
    fireEvent.click(screen.getByRole('button', { name: 'Analizar cobranza' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/agentes/predicciones/analizar-cobranza/', {}),
    );
    unmount();

    await new Promise((r) => setTimeout(r, 40));
    expect(get).not.toHaveBeenCalledWith('/agentes/ejecuciones/ej-1/');
  });

  it('valida el ID del gasto antes de clasificar', async () => {
    renderPage();
    await screen.findByText('oficina');
    fireEvent.click(screen.getByRole('button', { name: 'Clasificar' }));
    expect(await screen.findByText(/Indique el ID del gasto/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('clasifica un gasto enviando el payload y espera ejecución completada', async () => {
    vi.mocked(post).mockResolvedValue({
      ...ejecucionBase,
      agente: 'clasificador_gastos',
      estado: 'completado',
      resultado: { categoria: 'oficina', aplicado: false },
    });
    renderPage();
    await screen.findByText('oficina');
    fireEvent.change(screen.getByLabelText('ID del gasto'), { target: { value: 'g1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Clasificar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/agentes/predicciones/clasificar-gasto/', {
        gasto_id: 'g1',
        aplicar: false,
      }),
    );
    expect(await screen.findByText(/Clasificación de gasto/)).toBeInTheDocument();
  });

  it('muestra un error cuando el análisis de reorden falla al encolar', async () => {
    vi.mocked(post).mockRejectedValue(new Error('{"detail":"falló"}'));
    renderPage();
    await screen.findByText('oficina');
    fireEvent.click(screen.getByRole('button', { name: 'Analizar reorden' }));
    expect(await screen.findByText(/falló/)).toBeInTheDocument();
  });

  it('muestra el estado vacío cuando no hay predicciones y tolera precision null', async () => {
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/agentes/predicciones/metricas-clasificador')) {
        return Promise.resolve({
          total: 0,
          precision: null,
          confianza_promedio: null,
        });
      }
      if (url.startsWith('/agentes/predicciones')) return Promise.resolve([]);
      return Promise.resolve([]);
    });
    renderPage();
    expect(
      await screen.findByText('Sin predicciones registradas todavía.'),
    ).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2);
  });

  it('muestra la tarjeta de Consumo LLM con totales Decimal USD y desglose por uso y modelo', async () => {
    renderPage();
    const seccion = await screen.findByTestId('consumo-llm-section');
    expect(within(seccion).getByText('Consumo LLM (Tokens y Costo USD)')).toBeInTheDocument();
    expect(await within(seccion).findByText('$0.013500 USD')).toBeInTheDocument();
    expect(within(seccion).getByText('1,500')).toBeInTheDocument();
    expect(within(seccion).getByText('600')).toBeInTheDocument();
    expect(within(seccion).getByText('245 ms')).toBeInTheDocument();
    expect(within(seccion).getByText(/Asistente Chat: 2/)).toBeInTheDocument();
    expect(within(seccion).getByText(/modelo-sonnet-test: 2/)).toBeInTheDocument();
  });

  it('muestra estado vacío cuando no hay consumo LLM registrado', async () => {
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/agentes/consumo-llm/resumen')) {
        return Promise.resolve({
          llamadas: 0,
          tokens_entrada_total: 0,
          tokens_salida_total: 0,
          costo_total_usd: '0.000000',
          latencia_promedio_ms: 0,
          por_modelo: [],
          por_uso: [],
        });
      }
      if (url.startsWith('/agentes/predicciones/metricas-clasificador'))
        return Promise.resolve(metricas);
      if (url.startsWith('/agentes/predicciones'))
        return Promise.resolve([prediccionPendiente]);
      return Promise.resolve([]);
    });

    renderPage();
    expect(await screen.findByText('Sin consumo LLM registrado todavía.')).toBeInTheDocument();
  });

  it('muestra mensaje limpio si falla la carga de consumo LLM sin romper la página', async () => {
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/agentes/consumo-llm/resumen')) {
        return Promise.reject(new Error('500'));
      }
      if (url.startsWith('/agentes/predicciones/metricas-clasificador'))
        return Promise.resolve(metricas);
      if (url.startsWith('/agentes/predicciones'))
        return Promise.resolve([prediccionPendiente]);
      return Promise.resolve([]);
    });

    renderPage();
    expect(await screen.findByText('oficina')).toBeInTheDocument();
    expect(
      await screen.findByText('No se pudo cargar el resumen de consumo LLM.'),
    ).toBeInTheDocument();
  });
});
