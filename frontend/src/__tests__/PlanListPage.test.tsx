import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  fetchText: vi.fn(),
}));

import { get } from '../services/api';
import PlanListPage from '../pages/SaaS/PlanListPage';

const mockPlanes = [
  {
    id_plan: 'p1',
    nombre: 'Starter',
    nivel: 'STARTER',
    descripcion: '',
    precio_mensual: '10.00',
    precio_anual: '100.00',
    max_usuarios: 5,
    max_empresas: 1,
    max_documentos_mes: 100,
    permite_ia: false,
    permite_api: false,
    permite_reportes_avanzados: false,
    permite_multimoneda: false,
    soporte: 'email',
    activo: true,
    fecha_creacion: '',
    fecha_actualizacion: '',
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PlanListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PlanListPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renderiza la lista de planes tras cargar', async () => {
    vi.mocked(get).mockResolvedValue(mockPlanes);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Starter')).toBeInTheDocument();
    });
  });

  it('muestra el botón de nuevo plan y el toggle de inactivos', async () => {
    vi.mocked(get).mockResolvedValue([]);
    renderPage();
    expect(screen.getByRole('button', { name: /nuevo plan/i })).toBeInTheDocument();
    expect(screen.getByText(/mostrar planes inactivos/i)).toBeInTheDocument();
  });
});
