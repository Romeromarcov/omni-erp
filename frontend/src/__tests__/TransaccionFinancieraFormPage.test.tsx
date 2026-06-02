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

const postMock = vi.fn().mockResolvedValue({});
vi.mock('../services/api', () => ({
  get: vi.fn().mockResolvedValue({}),
  post: (...args: unknown[]) => postMock(...args),
}));

vi.mock('../services/empresas', () => ({
  fetchEmpresas: vi.fn().mockResolvedValue([{ id_empresa: 'e1' }]),
}));

vi.mock('../services/monedasEmpresaActiva', () => ({
  fetchMonedasEmpresaActivas: vi.fn().mockResolvedValue([]),
}));

vi.mock('../services/metodosPagoEmpresaActiva', () => ({
  fetchMetodosPagoEmpresaActivos: vi.fn().mockResolvedValue([]),
}));

import TransaccionFinancieraFormPage from '../pages/Finanzas/TransaccionFinanciera/TransaccionFinancieraFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TransaccionFinancieraFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('TransaccionFinancieraFormPage (react-hook-form + zod)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('blocks submit and shows validation when required fields are empty', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole('button', { name: /registrar transacción/i }));
    await waitFor(() => {
      expect(screen.getByText(/la fecha es obligatoria/i)).toBeInTheDocument();
      expect(screen.getByText(/el monto es obligatorio/i)).toBeInTheDocument();
    });
    expect(postMock).not.toHaveBeenCalled();
  });
});
