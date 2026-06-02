import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock, useParams: () => ({}) };
});

const createMock = vi.fn().mockResolvedValue({});
vi.mock('../services/plantillasService', () => ({
  createPlantillaMaestro: (...args: unknown[]) => createMock(...args),
  updatePlantillaMaestro: vi.fn(),
  getPlantillasMaestro: vi.fn().mockResolvedValue([]),
}));

vi.mock('../services/metodosPagoEmpresaActiva', () => ({
  fetchMetodosPagoEmpresaActivos: vi.fn().mockResolvedValue([
    { id_metodo_pago: 'mp1', nombre: 'Efectivo' },
  ]),
}));

vi.mock('../services/monedasEmpresaActiva', () => ({
  fetchMonedasEmpresaActivas: vi.fn().mockResolvedValue([
    { id_moneda: 'm1', nombre: 'Bolívar', simbolo: 'Bs' },
  ]),
}));

import PlantillaMaestroFormPage from '../pages/Finanzas/Cajas/PlantillaMaestroFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PlantillaMaestroFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('PlantillaMaestroFormPage (react-hook-form + zod)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'e1');
  });

  it('blocks submit and shows validation when nombre is empty', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole('button', { name: /crear/i }));
    await waitFor(() => {
      expect(screen.getByText(/el nombre es obligatorio/i)).toBeInTheDocument();
    });
    expect(createMock).not.toHaveBeenCalled();
  });
});
