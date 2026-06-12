import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/manufacturaService', () => ({
  manufacturaService: {
    getMrp: vi.fn(),
  },
}));

vi.mock('../services/almacenesService', () => ({
  almacenesService: {
    getAll: vi.fn(),
  },
}));

import { manufacturaService } from '../services/manufacturaService';
import { almacenesService } from '../services/almacenesService';
import MrpOrdenPage from '../pages/Manufactura/MrpOrdenPage';

const mrpConFaltantes = {
  orden_id: 'of-1',
  cantidad: '10.00',
  faltantes: [
    {
      producto_id: 'mat-1',
      producto: 'Madera de pino',
      requerido: '40.00',
      disponible: '15.00',
      a_comprar: '25.00',
    },
    {
      producto_id: 'mat-2',
      producto: 'Tornillos 3"',
      requerido: '200.00',
      disponible: '0.00',
      a_comprar: '200.00',
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/manufactura/ordenes/of-1/mrp']}>
        <Routes>
          <Route path="/manufactura/ordenes/:id/mrp" element={<MrpOrdenPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('MrpOrdenPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(almacenesService.getAll).mockResolvedValue([
      { id_almacen: 'alm-1', nombre_almacen: 'Principal', id_empresa: 'emp-1' },
    ]);
    vi.mocked(manufacturaService.getMrp).mockResolvedValue(mrpConFaltantes);
  });

  afterEach(() => {
    cleanup();
  });

  it('no calcula nada hasta pulsar "Calcular MRP" (acción explícita)', async () => {
    renderPage();
    expect(await screen.findByRole('button', { name: /calcular mrp/i })).toBeInTheDocument();
    expect(manufacturaService.getMrp).not.toHaveBeenCalled();
  });

  it('calcula el MRP y muestra la tabla de faltantes', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /calcular mrp/i }));

    expect(await screen.findByText('Madera de pino')).toBeInTheDocument();
    expect(screen.getByText('Tornillos 3"')).toBeInTheDocument();
    // Cantidades exactas tal como llegan del backend (strings, R-CODE-4).
    expect(screen.getByText('40.00')).toBeInTheDocument();
    expect(screen.getByText('15.00')).toBeInTheDocument();
    expect(screen.getByText('25.00')).toBeInTheDocument();
    expect(manufacturaService.getMrp).toHaveBeenCalledWith('of-1', { almacenId: undefined });
    // Tras calcular, el botón pasa a "Recalcular".
    expect(screen.getByRole('button', { name: /recalcular/i })).toBeInTheDocument();
  });

  it('filtra por almacén cuando se selecciona uno', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByLabelText(/almacén \(opcional\)/i));
    await user.click(await screen.findByRole('option', { name: 'Principal' }));
    await user.click(screen.getByRole('button', { name: /calcular mrp/i }));
    await waitFor(() =>
      expect(manufacturaService.getMrp).toHaveBeenCalledWith('of-1', { almacenId: 'alm-1' }),
    );
  });

  it('muestra el aviso de éxito cuando no hay faltantes', async () => {
    vi.mocked(manufacturaService.getMrp).mockResolvedValue({
      orden_id: 'of-1',
      cantidad: '10.00',
      faltantes: [],
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /calcular mrp/i }));
    expect(
      await screen.findByText(/no hay faltantes: el stock cubre la orden completa/i),
    ).toBeInTheDocument();
  });

  it('muestra el 400 del backend (p. ej. OF sin lista de materiales)', async () => {
    vi.mocked(manufacturaService.getMrp).mockRejectedValue(
      new Error(JSON.stringify({ error: 'La orden no tiene lista de materiales asociada.' })),
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /calcular mrp/i }));
    expect(
      await screen.findByText('La orden no tiene lista de materiales asociada.'),
    ).toBeInTheDocument();
  });
});
