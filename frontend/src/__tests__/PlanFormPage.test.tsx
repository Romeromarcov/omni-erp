import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
}));

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

import { get, post } from '../services/api';
import PlanFormPage from '../pages/SaaS/PlanFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PlanFormPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PlanFormPage (react-hook-form + zod)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockResolvedValue([]);
    vi.mocked(post).mockResolvedValue({});
  });

  it('rechaza un precio mal formado y no envía', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByLabelText(/^nombre/i), 'Plan Demo');
    const precio = screen.getByLabelText(/precio mensual/i);
    await user.clear(precio);
    await user.type(precio, '10,5');
    await user.click(screen.getByRole('button', { name: /guardar/i }));
    await waitFor(() => {
      expect(screen.getByText(/precio mensual inválido/i)).toBeInTheDocument();
    });
    expect(post).not.toHaveBeenCalled();
  });

  it('exige el nombre', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole('button', { name: /guardar/i }));
    await waitFor(() => {
      expect(screen.getByText(/el nombre es obligatorio/i)).toBeInTheDocument();
    });
    expect(post).not.toHaveBeenCalled();
  });

  it('envía una vez con datos válidos (precio como string)', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByLabelText(/^nombre/i), 'Plan Demo');
    const precio = screen.getByLabelText(/precio mensual/i);
    await user.clear(precio);
    await user.type(precio, '29.90');
    await user.click(screen.getByRole('button', { name: /guardar/i }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(post).mock.calls[0][1] as { precio_mensual: unknown };
    expect(payload.precio_mensual).toBe('29.90');
  });
});
