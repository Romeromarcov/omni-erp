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
import ProveedorIntegracionFormPage from '../pages/SaaS/ProveedorIntegracionFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ProveedorIntegracionFormPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProveedorIntegracionFormPage (react-hook-form + zod)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockResolvedValue([]);
    vi.mocked(post).mockResolvedValue({});
  });

  it('muestra errores por campo y no envía con el formulario vacío', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole('button', { name: /guardar/i }));
    await waitFor(() => {
      expect(screen.getByText(/el código es obligatorio/i)).toBeInTheDocument();
      expect(screen.getByText(/el nombre es obligatorio/i)).toBeInTheDocument();
    });
    expect(post).not.toHaveBeenCalled();
  });

  it('rechaza un código con mayúsculas/espacios (regex)', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByLabelText(/código del conector/i), 'Odoo ERP');
    await user.type(screen.getByLabelText(/^nombre/i), 'Odoo');
    await user.click(screen.getByRole('button', { name: /guardar/i }));
    await waitFor(() => {
      expect(screen.getByText(/solo admite minúsculas/i)).toBeInTheDocument();
    });
    expect(post).not.toHaveBeenCalled();
  });

  it('envía una vez con datos válidos', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByLabelText(/código del conector/i), 'odoo');
    await user.type(screen.getByLabelText(/^nombre/i), 'Odoo');
    await user.click(screen.getByRole('button', { name: /guardar/i }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  });
});
