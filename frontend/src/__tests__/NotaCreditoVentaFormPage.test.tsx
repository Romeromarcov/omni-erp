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
vi.mock('../services/ventas', () => ({
  notaCreditoVentaService: {
    create: (...args: unknown[]) => createMock(...args),
    update: vi.fn(),
    getById: vi.fn(),
  },
}));

vi.mock('../services/clientesService', () => ({
  fetchClientes: vi.fn().mockResolvedValue([
    { id_cliente: 'c1', razon_social: 'Cliente Uno', rif: 'J-123', telefono: '555' },
  ]),
}));

vi.mock('../services/productosService', () => ({
  fetchProductos: vi.fn().mockResolvedValue([
    { id_producto: 'p1', nombre_producto: 'Producto Uno' },
  ]),
}));

import NotaCreditoVentaFormPage from '../pages/Ventas/NotasCreditoVenta/NotaCreditoVentaFormPage';

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NotaCreditoVentaFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('NotaCreditoVentaFormPage (react-hook-form + zod)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('blocks submit and shows validation when no cliente and no detalles', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole('button', { name: /crear/i }));
    await waitFor(() => {
      expect(screen.getByText(/cliente es obligatorio/i)).toBeInTheDocument();
      expect(screen.getByText(/al menos un producto/i)).toBeInTheDocument();
    });
    expect(createMock).not.toHaveBeenCalled();
  });
});
