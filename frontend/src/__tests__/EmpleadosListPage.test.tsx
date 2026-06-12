import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/rrhhService', () => ({
  rrhhService: {
    getEmpleadosPaginated: vi.fn(),
    getCargos: vi.fn(),
  },
}));

import { rrhhService } from '../services/rrhhService';
import EmpleadosListPage from '../pages/RRHH/EmpleadosListPage';

const empleados = [
  {
    id: 1,
    empresa: 'emp-1',
    referencia_externa: null,
    documento_json: { salario_mensual: '500.00' },
    nombre: 'Ana',
    apellido: 'Pérez',
    cedula: 'V-12345678',
    cargo: 3,
    fecha_ingreso: '2024-01-15',
    activo: true,
    contacto: null,
  },
  {
    id: 2,
    empresa: 'emp-1',
    referencia_externa: null,
    documento_json: null,
    nombre: 'Luis',
    apellido: 'Gómez',
    cedula: 'V-87654321',
    cargo: null,
    fecha_ingreso: '2023-05-01',
    activo: false,
    contacto: null,
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/rrhh/empleados']}>
        <Routes>
          <Route path="/rrhh/empleados" element={<EmpleadosListPage />} />
          <Route path="/rrhh/empleados/nuevo" element={<div>form-nuevo</div>} />
          <Route path="/rrhh/empleados/:id" element={<div>detalle-empleado</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('EmpleadosListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(rrhhService.getEmpleadosPaginated).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: empleados,
    });
    vi.mocked(rrhhService.getCargos).mockResolvedValue([
      { id: 3, empresa: null, nombre: 'Vendedora', descripcion: null, activo: true },
    ]);
  });

  afterEach(() => {
    cleanup();
  });

  it('muestra empleados con nombre completo, cargo resuelto y estado', async () => {
    renderPage();
    expect(await screen.findByText('Ana Pérez')).toBeInTheDocument();
    expect(screen.getByText('V-12345678')).toBeInTheDocument();
    expect(await screen.findByText('Vendedora')).toBeInTheDocument();
    // Sin cargo → guion; inactivo → chip Inactivo.
    expect(screen.getByText('Luis Gómez')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('Inactivo')).toBeInTheDocument();
    expect(screen.getByText('Activo')).toBeInTheDocument();
  });

  it('navega al formulario de creación y al detalle', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Ana Pérez');

    await user.click(screen.getAllByRole('button', { name: /ver detalle/i })[0]);
    expect(await screen.findByText('detalle-empleado')).toBeInTheDocument();
  });

  it('el botón Nuevo empleado lleva al formulario', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Ana Pérez');
    await user.click(screen.getByRole('button', { name: /nuevo empleado/i }));
    expect(await screen.findByText('form-nuevo')).toBeInTheDocument();
  });

  it('muestra el vacío cuando no hay empleados', async () => {
    vi.mocked(rrhhService.getEmpleadosPaginated).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    renderPage();
    expect(await screen.findByText(/no hay empleados registrados/i)).toBeInTheDocument();
  });
});
