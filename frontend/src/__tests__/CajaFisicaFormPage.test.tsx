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
vi.mock('../services/cajasFisicasService', () => ({
  cajasFisicasService: {
    createCajaFisica: (...args: unknown[]) => createMock(...args),
    updateCajaFisica: vi.fn(),
    getCajaFisica: vi.fn(),
    getTipoCajaChoices: vi.fn().mockResolvedValue([{ value: 'REGISTRADORA', display: 'Registradora' }]),
  },
}));

vi.mock('../services/monedasEmpresaActiva', () => ({
  fetchMonedasEmpresaActivas: vi.fn().mockResolvedValue([
    { id_moneda: 'm1', nombre: 'Bolívar', codigo_iso: 'VES' },
  ]),
}));

import CajaFisicaFormPage from '../pages/Finanzas/Cajas/CajaFisicaFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CajaFisicaFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CajaFisicaFormPage (react-hook-form + zod)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'e1');
  });

  it('blocks submit and shows validation when nombre and moneda are empty', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole('button', { name: /crear/i }));
    await waitFor(() => {
      expect(screen.getByText(/el nombre es obligatorio/i)).toBeInTheDocument();
      expect(screen.getByText(/debe seleccionar una moneda/i)).toBeInTheDocument();
    });
    expect(createMock).not.toHaveBeenCalled();
  });
});
