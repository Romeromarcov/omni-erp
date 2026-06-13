import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/rrhhService', () => ({
  rrhhService: {
    getEmpleado: vi.fn(),
    getCargos: vi.fn(),
  },
}));

import { rrhhService } from '../services/rrhhService';
import EmpleadoDetailPage from '../pages/RRHH/EmpleadoDetailPage';

const empleado = {
  id: 1,
  empresa: 'emp-1',
  referencia_externa: null,
  documento_json: { salario_mensual: '500.5' },
  nombre: 'Ana',
  apellido: 'Pérez',
  cedula: 'V-12345678',
  cargo: 3,
  fecha_ingreso: '2024-01-15',
  activo: true,
  contacto: null,
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/rrhh/empleados/1']}>
        <Routes>
          <Route path="/rrhh/empleados/:id" element={<EmpleadoDetailPage />} />
          <Route path="/rrhh/empleados/:id/editar" element={<div>form-editar</div>} />
          <Route path="/rrhh/empleados" element={<div>lista-empleados</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('EmpleadoDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(rrhhService.getEmpleado).mockResolvedValue(empleado);
    vi.mocked(rrhhService.getCargos).mockResolvedValue([
      { id: 3, empresa: null, nombre: 'Vendedora', descripcion: null, activo: true },
    ]);
  });

  afterEach(() => {
    cleanup();
  });

  it('muestra los datos básicos con el salario formateado a 2 decimales', async () => {
    renderPage();
    expect(await screen.findByText('Ana Pérez')).toBeInTheDocument();
    expect(screen.getByText(/V-12345678/)).toBeInTheDocument();
    expect(await screen.findByText('Vendedora')).toBeInTheDocument();
    // '500.5' (string decimal) → '500.50' con decimal.js, nunca float.
    expect(screen.getByText('500.50')).toBeInTheDocument();
    expect(screen.getByText('2024-01-15')).toBeInTheDocument();
    expect(screen.getByText('Activo')).toBeInTheDocument();
  });

  it('indica cuando el empleado no tiene salario definido', async () => {
    vi.mocked(rrhhService.getEmpleado).mockResolvedValue({
      ...empleado,
      documento_json: null,
      cargo: null,
    });
    renderPage();
    expect(await screen.findByText(/sin salario definido/i)).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('navega a editar', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Ana Pérez');
    await user.click(screen.getByRole('button', { name: /editar/i }));
    expect(await screen.findByText('form-editar')).toBeInTheDocument();
  });
});
