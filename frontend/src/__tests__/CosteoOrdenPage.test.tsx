import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/manufacturaService', () => ({
  manufacturaService: {
    getCosteo: vi.fn(),
  },
}));

import { manufacturaService } from '../services/manufacturaService';
import CosteoOrdenPage from '../pages/Manufactura/CosteoOrdenPage';

const costeo = {
  orden_id: 'of-1',
  estado: 'en_proceso',
  costo: {
    costo_materiales: '100.5000',
    mano_obra: '20.0000',
    costos_indirectos: '12.0500',
    costo_total: '132.5500',
    costo_unitario: '13.2550',
  },
  etapas: [
    {
      id: 'et-1',
      orden_produccion: 'of-1',
      etapa: 'cat-1',
      etapa_codigo: 'corte',
      etapa_nombre: 'Corte',
      orden: 1,
      estado: 'completada' as const,
      horas_trabajadas: '2.00',
      tarifa_hora: '4.0000',
      cantidad_destajo: '10.0000',
      pago_destajo: '5.0000',
      costo_mano_obra: '13.0000',
      completada_por: 7,
      fecha_completada: '2026-06-02T10:00:00Z',
      observaciones: '',
    },
    {
      id: 'et-2',
      orden_produccion: 'of-1',
      etapa: 'cat-2',
      etapa_codigo: 'ensamble',
      etapa_nombre: 'Ensamble',
      orden: 2,
      estado: 'pendiente' as const,
      horas_trabajadas: '0',
      tarifa_hora: '0',
      cantidad_destajo: '0',
      pago_destajo: '0',
      costo_mano_obra: '0',
      completada_por: null,
      fecha_completada: null,
      observaciones: '',
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/manufactura/ordenes/of-1/costeo']}>
        <Routes>
          <Route path="/manufactura/ordenes/:id/costeo" element={<CosteoOrdenPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CosteoOrdenPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(manufacturaService.getCosteo).mockResolvedValue(costeo);
  });

  afterEach(() => {
    cleanup();
  });

  it('muestra el desglose con montos EXACTOS formateados con decimal.js', async () => {
    renderPage();
    // toFixedStr(2) sobre los strings del backend — sin aritmética float.
    expect(await screen.findByText('100.50')).toBeInTheDocument(); // materiales
    expect(screen.getAllByText('20.00').length).toBeGreaterThan(0); // mano de obra
    expect(screen.getByText('12.05')).toBeInTheDocument(); // overhead
    expect(screen.getByText('132.55')).toBeInTheDocument(); // total
    expect(screen.getByText('13.2550')).toBeInTheDocument(); // unitario a 4 decimales
  });

  it('calcula la participación porcentual con Decimal (sin float)', async () => {
    renderPage();
    await screen.findByText('132.55');
    // 100.5000 / 132.5500 × 100 = 75.82 → 75.8%
    expect(screen.getByText('75.8%')).toBeInTheDocument();
    expect(screen.getByText('15.1%')).toBeInTheDocument(); // mano de obra
    expect(screen.getByText('9.1%')).toBeInTheDocument(); // overhead
    expect(screen.getByText('100.0%')).toBeInTheDocument();
  });

  it('lista solo las etapas completadas en la tabla de mano de obra', async () => {
    renderPage();
    expect(await screen.findByText(/1\. Corte/)).toBeInTheDocument();
    expect(screen.queryByText(/2\. Ensamble/)).not.toBeInTheDocument();
    expect(screen.getByText('13.00')).toBeInTheDocument(); // costo MO de Corte
    expect(screen.getByText('5.00')).toBeInTheDocument(); // pago destajo
  });

  it('muestra el error del backend si el costeo falla', async () => {
    vi.mocked(manufacturaService.getCosteo).mockRejectedValue(
      new Error(JSON.stringify({ error: 'La orden no tiene consumos registrados.' })),
    );
    renderPage();
    expect(await screen.findByText('La orden no tiene consumos registrados.')).toBeInTheDocument();
  });
});
