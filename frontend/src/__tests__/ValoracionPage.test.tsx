import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/inventarioService', () => ({
  reportesInventarioService: { valoracion: vi.fn() },
}));

import { reportesInventarioService } from '../services/inventarioService';
import ValoracionPage from '../pages/Inventario/ValoracionPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ValoracionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ValoracionPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('muestra las filas de valoración', async () => {
    vi.mocked(reportesInventarioService.valoracion).mockResolvedValue([
      {
        producto_id: 'p1', producto: 'Aceite', almacen_id: 'a1', almacen: 'Central',
        metodo: 'PROMEDIO', cantidad: '15.0000', valor_total: '225.0000', costo_promedio: '15.0000',
      },
    ]);
    renderPage();
    expect(await screen.findByText('Aceite')).toBeInTheDocument();
    expect(screen.getByText('225.0000')).toBeInTheDocument();
    expect(screen.getByText('PROMEDIO')).toBeInTheDocument();
  });

  it('muestra vacío cuando no hay existencias', async () => {
    vi.mocked(reportesInventarioService.valoracion).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText('Sin existencias valoradas.')).toBeInTheDocument();
  });
});
