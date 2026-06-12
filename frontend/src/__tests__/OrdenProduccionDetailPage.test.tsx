import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/manufacturaService', () => ({
  manufacturaService: {
    getOrden: vi.fn(),
    getEtapas: vi.fn(),
    avanzarEtapa: vi.fn(),
    completarOrden: vi.fn(),
  },
}));

vi.mock('../services/almacenesService', () => ({
  almacenesService: {
    getAll: vi.fn(),
  },
}));

import { manufacturaService } from '../services/manufacturaService';
import { almacenesService } from '../services/almacenesService';
import OrdenProduccionDetailPage from '../pages/Manufactura/OrdenProduccionDetailPage';

const orden = {
  id: 'of-1',
  producto: 'prod-1',
  cantidad: '10.00',
  fecha_inicio: '2026-06-01',
  fecha_fin: null,
  estado: 'en_proceso',
  lista_materiales: 'bom-1',
  ruta_produccion: null,
  referencia_externa: 'OF-0001',
  observaciones: '',
};

const etapaBase = {
  orden_produccion: 'of-1',
  tarifa_hora: '0',
  cantidad_destajo: '0',
  completada_por: null,
  observaciones: '',
};

const etapas = [
  {
    ...etapaBase,
    id: 'et-1',
    etapa: 'cat-1',
    etapa_codigo: 'corte',
    etapa_nombre: 'Corte',
    orden: 1,
    estado: 'completada' as const,
    horas_trabajadas: '2.00',
    pago_destajo: '5.0000',
    costo_mano_obra: '13.0000',
    completada_por: 7,
    fecha_completada: '2026-06-02T10:00:00Z',
  },
  {
    ...etapaBase,
    id: 'et-2',
    etapa: 'cat-2',
    etapa_codigo: 'ensamble',
    etapa_nombre: 'Ensamble',
    orden: 2,
    estado: 'pendiente' as const,
    horas_trabajadas: '0',
    pago_destajo: '0',
    costo_mano_obra: '0',
    fecha_completada: null,
  },
  {
    ...etapaBase,
    id: 'et-3',
    etapa: 'cat-3',
    etapa_codigo: 'lijado',
    etapa_nombre: 'Lijado',
    orden: 3,
    estado: 'pendiente' as const,
    horas_trabajadas: '0',
    pago_destajo: '0',
    costo_mano_obra: '0',
    fecha_completada: null,
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/manufactura/ordenes/of-1']}>
        <FeedbackProvider>
          <Routes>
            <Route path="/manufactura/ordenes/:id" element={<OrdenProduccionDetailPage />} />
          </Routes>
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('OrdenProduccionDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(manufacturaService.getOrden).mockResolvedValue(orden);
    vi.mocked(manufacturaService.getEtapas).mockResolvedValue(etapas);
    vi.mocked(almacenesService.getAll).mockResolvedValue([
      { id_almacen: 'alm-1', nombre_almacen: 'Principal', id_empresa: 'emp-1' },
    ]);
  });

  afterEach(() => {
    cleanup();
  });

  it('muestra la secuencia de etapas con su estado', async () => {
    renderPage();
    expect(await screen.findByText(/1\. Corte/)).toBeInTheDocument();
    expect(screen.getByText(/2\. Ensamble/)).toBeInTheDocument();
    expect(screen.getByText(/3\. Lijado/)).toBeInTheDocument();
    expect(screen.getByText('Completada')).toBeInTheDocument();
    expect(screen.getAllByText('Pendiente')).toHaveLength(2);
    // Datos de la etapa completada: horas y mano de obra con decimales fijos.
    expect(screen.getByText(/Horas trabajadas: 2\.00/)).toBeInTheDocument();
    expect(screen.getByText(/Mano de obra: 13\.00/)).toBeInTheDocument();
  });

  it('avanza la siguiente etapa con horas y destajo (transición auditada)', async () => {
    const user = userEvent.setup();
    vi.mocked(manufacturaService.avanzarEtapa).mockResolvedValue({
      estado_orden: 'en_proceso',
      etapa: { ...etapas[1], estado: 'completada' },
      etapas_pendientes: 1,
    });
    renderPage();
    await screen.findByText(/1\. Corte/);

    await user.click(screen.getByRole('button', { name: /avanzar etapa/i }));
    // El diálogo apunta a la siguiente etapa pendiente (Ensamble).
    expect(await screen.findByText(/Avanzar etapa — Ensamble/)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/horas trabajadas/i), '3.5');
    await user.type(screen.getByLabelText(/tarifa por hora/i), '4.00');
    await user.type(screen.getByLabelText(/cantidad a destajo/i), '10');
    await user.click(screen.getByRole('button', { name: /confirmar/i }));

    await waitFor(() =>
      expect(manufacturaService.avanzarEtapa).toHaveBeenCalledWith('of-1', {
        horas_trabajadas: '3.5',
        tarifa_hora: '4.00',
        cantidad_destajo: '10',
        observaciones: '',
      }),
    );
  });

  it('valida con zod que las horas sean un decimal no negativo', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/1\. Corte/);
    await user.click(screen.getByRole('button', { name: /avanzar etapa/i }));
    await user.type(await screen.findByLabelText(/horas trabajadas/i), 'abc');
    await user.click(screen.getByRole('button', { name: /confirmar/i }));
    expect(
      await screen.findByText(/las horas deben ser un número mayor o igual a 0/i),
    ).toBeInTheDocument();
    expect(manufacturaService.avanzarEtapa).not.toHaveBeenCalled();
  });

  it('muestra el 400 del backend al avanzar (lock de doble avance)', async () => {
    const user = userEvent.setup();
    vi.mocked(manufacturaService.avanzarEtapa).mockRejectedValue(
      new Error(JSON.stringify({ error: 'La orden no tiene etapas pendientes.' })),
    );
    renderPage();
    await screen.findByText(/1\. Corte/);
    await user.click(screen.getByRole('button', { name: /avanzar etapa/i }));
    await user.click(await screen.findByRole('button', { name: /confirmar/i }));
    expect(await screen.findByText('La orden no tiene etapas pendientes.')).toBeInTheDocument();
  });

  it('muestra el 400 al completar la OF con etapas pendientes', async () => {
    const user = userEvent.setup();
    vi.mocked(manufacturaService.completarOrden).mockRejectedValue(
      new Error(
        JSON.stringify({ error: 'No se puede completar la orden: quedan 2 etapas pendientes.' }),
      ),
    );
    renderPage();
    await screen.findByText(/1\. Corte/);
    await user.click(screen.getByRole('button', { name: /completar of/i }));

    // Selecciona el almacén (obligatorio) y confirma.
    await user.click(await screen.findByLabelText(/almacén/i));
    await user.click(await screen.findByRole('option', { name: 'Principal' }));
    await user.click(screen.getByRole('button', { name: /confirmar/i }));

    expect(
      await screen.findByText('No se puede completar la orden: quedan 2 etapas pendientes.'),
    ).toBeInTheDocument();
    expect(manufacturaService.completarOrden).toHaveBeenCalledWith('of-1', { almacen_id: 'alm-1' });
  });

  it('deshabilita avanzar/completar si la orden está finalizada', async () => {
    vi.mocked(manufacturaService.getOrden).mockResolvedValue({ ...orden, estado: 'finalizada' });
    vi.mocked(manufacturaService.getEtapas).mockResolvedValue(
      etapas.map((e) => ({ ...e, estado: 'completada' as const })),
    );
    renderPage();
    await screen.findByText(/1\. Corte/);
    expect(screen.getByRole('button', { name: /avanzar etapa/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /completar of/i })).toBeDisabled();
  });
});
