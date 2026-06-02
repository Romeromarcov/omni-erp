import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

import { get, post } from '../services/api';
import MonedaFormPage from '../pages/Finanzas/Monedas/MonedaFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <MonedaFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('MonedaFormPage (react-hook-form + zod)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockResolvedValue([]);
    vi.mocked(post).mockResolvedValue({});
  });

  it('shows per-field helperText errors on empty submit', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole('button', { name: /crear/i }));
    await waitFor(() => {
      expect(screen.getByText(/el código iso debe tener al menos/i)).toBeInTheDocument();
      expect(screen.getByText(/el nombre debe tener al menos/i)).toBeInTheDocument();
      expect(screen.getByText(/el símbolo es obligatorio/i)).toBeInTheDocument();
    });
    expect(post).not.toHaveBeenCalled();
  });

  it('calls the mutation once with valid data', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByLabelText(/código iso/i), 'USD');
    await user.type(screen.getByLabelText(/nombre/i), 'Dólar Americano');
    await user.type(screen.getByLabelText(/símbolo/i), '$');
    await user.click(screen.getByRole('button', { name: /crear/i }));
    await waitFor(() => {
      expect(post).toHaveBeenCalledTimes(1);
    });
    expect(post).toHaveBeenCalledWith('/finanzas/monedas/', expect.objectContaining({
      codigo_iso: 'USD',
      nombre: 'Dólar Americano',
      simbolo: '$',
    }));
  });
});
