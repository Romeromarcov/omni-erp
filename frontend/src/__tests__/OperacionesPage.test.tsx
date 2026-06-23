import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/inventarioService', () => ({
  recepcionesService: { list: vi.fn(), create: vi.fn(), confirmStep: vi.fn() },
  entregasService: { list: vi.fn(), create: vi.fn(), confirmStep: vi.fn() },
  productoInventarioService: { getAll: vi.fn() },
}));
vi.mock('../services/almacenesService', () => ({
  almacenesService: { getAll: vi.fn() },
}));

import { recepcionesService, productoInventarioService } from '../services/inventarioService';
import { almacenesService } from '../services/almacenesService';
import RecepcionesPage from '../pages/Inventario/RecepcionesPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <RecepcionesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const opEnProceso = {
  id_operacion: 'op-1',
  numero: 'REC-000001',
  tipo_operacion: 'RECEPCION',
  origen_tipo: 'PURCHASE',
  origen_id: null,
  id_almacen: 'alm-1',
  id_almacen_contraparte: null,
  estado: 'EN_PROCESO',
  motivo: '',
  fecha: '2026-06-23T10:00:00Z',
  pasos: [
    { id_operacion_paso: 's1', secuencia: 1, nombre_paso: 'Confirmación', confirmado: false, fecha_confirmacion: null },
    { id_operacion_paso: 's2', secuencia: 2, nombre_paso: 'Calidad', confirmado: false, fecha_confirmacion: null },
  ],
  lineas: [],
};

describe('OperacionesPage (recepciones)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(almacenesService.getAll).mockResolvedValue([
      { id_almacen: 'alm-1', nombre_almacen: 'Central', id_empresa: 'e1' },
    ]);
    vi.mocked(productoInventarioService.getAll).mockResolvedValue([]);
  });

  it('lista operaciones y muestra el stepper con sólo el primer paso confirmable', async () => {
    vi.mocked(recepcionesService.list).mockResolvedValue([opEnProceso] as never);

    renderPage();
    expect(await screen.findByText('Recepciones')).toBeInTheDocument();
    fireEvent.click(await screen.findByText('REC-000001'));

    // Pasos visibles; sólo un botón "Confirmar" (el del paso activo).
    expect(await screen.findByText('Confirmación')).toBeInTheDocument();
    expect(screen.getByText('Calidad')).toBeInTheDocument();
    const botones = screen.getAllByRole('button', { name: 'Confirmar' });
    expect(botones).toHaveLength(1);
  });

  it('confirmar un paso llama al servicio', async () => {
    vi.mocked(recepcionesService.list).mockResolvedValue([opEnProceso] as never);
    vi.mocked(recepcionesService.confirmStep).mockResolvedValue(opEnProceso as never);

    renderPage();
    fireEvent.click(await screen.findByText('REC-000001'));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }));

    await waitFor(() =>
      expect(recepcionesService.confirmStep).toHaveBeenCalledWith('op-1', 's1'),
    );
  });
});
