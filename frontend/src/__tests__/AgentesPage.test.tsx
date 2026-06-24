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

function setupGet(predicciones = [prediccionPendiente, prediccionAceptada]) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/agentes/predicciones/metricas-clasificador'))
      return Promise.resolve(metricas);
    if (url.startsWith('/agentes/predicciones')) return Promise.resolve(predicciones);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AgentesPage />
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

  it('dispara el análisis de cobranza', async () => {
    vi.mocked(post).mockResolvedValue({ sugerencias: [], total: 0 });
    renderPage();
    await screen.findByText('oficina');
    fireEvent.click(screen.getByRole('button', { name: 'Analizar cobranza' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/agentes/predicciones/analizar-cobranza/', {}),
    );
    expect(await screen.findByText(/Análisis de cobranza/)).toBeInTheDocument();
  });

  it('valida el ID del gasto antes de clasificar', async () => {
    renderPage();
    await screen.findByText('oficina');
    fireEvent.click(screen.getByRole('button', { name: 'Clasificar' }));
    expect(await screen.findByText(/Indique el ID del gasto/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('clasifica un gasto enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue({ categoria: 'oficina', aplicado: false });
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
  });

  it('muestra un error cuando el análisis de reorden falla', async () => {
    vi.mocked(post).mockRejectedValue(new Error('{"detail":"falló"}'));
    renderPage();
    await screen.findByText('oficina');
    fireEvent.click(screen.getByRole('button', { name: 'Analizar reorden' }));
    expect(await screen.findByText(/falló/)).toBeInTheDocument();
  });

  it('muestra el estado vacío cuando no hay predicciones', async () => {
    setupGet([]);
    renderPage();
    expect(
      await screen.findByText('Sin predicciones registradas todavía.'),
    ).toBeInTheDocument();
  });
});
