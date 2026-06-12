import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/rrhhService', () => ({
  rrhhService: {
    getEmpleado: vi.fn(),
    getCargos: vi.fn(),
    crearEmpleado: vi.fn(),
    actualizarEmpleado: vi.fn(),
  },
}));

import { rrhhService } from '../services/rrhhService';
import EmpleadoFormPage from '../pages/RRHH/EmpleadoFormPage';

const empleado = {
  id: 1,
  empresa: 'emp-1',
  referencia_externa: null,
  // `otra_clave` debe sobrevivir a la edición del salario (merge, no clobber).
  documento_json: { salario_mensual: '500.00', otra_clave: 'preservar' },
  nombre: 'Ana',
  apellido: 'Pérez',
  cedula: 'V-12345678',
  cargo: 3,
  fecha_ingreso: '2024-01-15',
  activo: true,
  contacto: null,
};

function renderPage(ruta: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={[ruta]}>
          <Routes>
            <Route path="/rrhh/empleados/nuevo" element={<EmpleadoFormPage />} />
            <Route path="/rrhh/empleados/:id/editar" element={<EmpleadoFormPage />} />
            <Route path="/rrhh/empleados/:id" element={<div>detalle-empleado</div>} />
            <Route path="/rrhh/empleados" element={<div>lista-empleados</div>} />
          </Routes>
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('EmpleadoFormPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    vi.mocked(rrhhService.getCargos).mockResolvedValue([
      { id: 3, empresa: null, nombre: 'Vendedora', descripcion: null, activo: true },
    ]);
    vi.mocked(rrhhService.getEmpleado).mockResolvedValue(empleado);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('crea el empleado con empresa activa y salario string en documento_json', async () => {
    vi.mocked(rrhhService.crearEmpleado).mockResolvedValue({ ...empleado, id: 7 });
    const user = userEvent.setup();
    renderPage('/rrhh/empleados/nuevo');

    await user.type(await screen.findByLabelText(/^nombre/i), 'Ana');
    await user.type(screen.getByLabelText(/apellido/i), 'Pérez');
    await user.type(screen.getByLabelText(/cédula/i), 'V-12345678');
    await user.type(screen.getByLabelText(/fecha de ingreso/i), '2024-01-15');
    await user.type(screen.getByLabelText(/salario mensual/i), '500.00');
    await user.click(screen.getByLabelText(/^cargo/i));
    await user.click(await screen.findByRole('option', { name: 'Vendedora' }));
    await user.click(screen.getByRole('button', { name: /crear empleado/i }));

    await waitFor(() =>
      expect(rrhhService.crearEmpleado).toHaveBeenCalledWith({
        empresa: 'emp-1',
        nombre: 'Ana',
        apellido: 'Pérez',
        cedula: 'V-12345678',
        cargo: 3,
        fecha_ingreso: '2024-01-15',
        activo: true,
        documento_json: { salario_mensual: '500.00' },
      }),
    );
    // Navega al detalle del empleado creado.
    expect(await screen.findByText('detalle-empleado')).toBeInTheDocument();
  });

  it('crea sin cargo ni salario con documento_json null', async () => {
    vi.mocked(rrhhService.crearEmpleado).mockResolvedValue({ ...empleado, id: 8 });
    const user = userEvent.setup();
    renderPage('/rrhh/empleados/nuevo');

    await user.type(await screen.findByLabelText(/^nombre/i), 'Luis');
    await user.type(screen.getByLabelText(/apellido/i), 'Gómez');
    await user.type(screen.getByLabelText(/cédula/i), 'V-1');
    await user.type(screen.getByLabelText(/fecha de ingreso/i), '2024-02-01');
    await user.click(screen.getByRole('button', { name: /crear empleado/i }));

    await waitFor(() =>
      expect(rrhhService.crearEmpleado).toHaveBeenCalledWith(
        expect.objectContaining({ cargo: null, documento_json: null }),
      ),
    );
  });

  it('valida los campos obligatorios y el salario decimal sin llamar a la API', async () => {
    const user = userEvent.setup();
    renderPage('/rrhh/empleados/nuevo');
    await screen.findByLabelText(/^nombre/i);

    await user.type(screen.getByLabelText(/salario mensual/i), 'abc');
    await user.click(screen.getByRole('button', { name: /crear empleado/i }));

    expect(await screen.findByText('El nombre es obligatorio')).toBeInTheDocument();
    expect(screen.getByText('El salario debe ser un número ≥ 0')).toBeInTheDocument();
    expect(rrhhService.crearEmpleado).not.toHaveBeenCalled();
  });

  it('edita: precarga los datos y PATCHea preservando otras claves del documento_json', async () => {
    vi.mocked(rrhhService.actualizarEmpleado).mockResolvedValue({ ...empleado });
    const user = userEvent.setup();
    renderPage('/rrhh/empleados/1/editar');

    const salario = await screen.findByLabelText(/salario mensual/i);
    await waitFor(() => expect(salario).toHaveValue('500.00'));
    expect(screen.getByLabelText(/^nombre/i)).toHaveValue('Ana');

    await user.clear(salario);
    await user.type(salario, '650.10');
    await user.click(screen.getByRole('button', { name: /guardar cambios/i }));

    await waitFor(() =>
      expect(rrhhService.actualizarEmpleado).toHaveBeenCalledWith('1', {
        nombre: 'Ana',
        apellido: 'Pérez',
        cedula: 'V-12345678',
        cargo: 3,
        fecha_ingreso: '2024-01-15',
        activo: true,
        documento_json: { salario_mensual: '650.10', otra_clave: 'preservar' },
      }),
    );
    const payload = vi.mocked(rrhhService.actualizarEmpleado).mock.calls[0][1];
    // PATCH parcial: nunca reenvía `empresa` (no se mueve de tenant).
    expect(payload).not.toHaveProperty('empresa');
  });

  it('al borrar el salario en edición elimina la clave y conserva el resto', async () => {
    vi.mocked(rrhhService.actualizarEmpleado).mockResolvedValue({ ...empleado });
    const user = userEvent.setup();
    renderPage('/rrhh/empleados/1/editar');

    const salario = await screen.findByLabelText(/salario mensual/i);
    await waitFor(() => expect(salario).toHaveValue('500.00'));
    await user.clear(salario);
    await user.click(screen.getByRole('button', { name: /guardar cambios/i }));

    await waitFor(() =>
      expect(rrhhService.actualizarEmpleado).toHaveBeenCalledWith(
        '1',
        expect.objectContaining({ documento_json: { otra_clave: 'preservar' } }),
      ),
    );
  });

  it('muestra el 400 del backend (cédula duplicada en la empresa)', async () => {
    vi.mocked(rrhhService.crearEmpleado).mockRejectedValue(
      new Error(
        JSON.stringify({ non_field_errors: ['Los campos empresa, cedula deben formar un conjunto único.'] }),
      ),
    );
    const user = userEvent.setup();
    renderPage('/rrhh/empleados/nuevo');

    await user.type(await screen.findByLabelText(/^nombre/i), 'Ana');
    await user.type(screen.getByLabelText(/apellido/i), 'Pérez');
    await user.type(screen.getByLabelText(/cédula/i), 'V-12345678');
    await user.type(screen.getByLabelText(/fecha de ingreso/i), '2024-01-15');
    await user.click(screen.getByRole('button', { name: /crear empleado/i }));

    expect(
      await screen.findByText(/los campos empresa, cedula deben formar un conjunto único/i),
    ).toBeInTheDocument();
  });

  it('sin empresa activa: advierte y deshabilita el submit en creación', async () => {
    localStorage.removeItem('id_empresa');
    renderPage('/rrhh/empleados/nuevo');
    expect(
      await screen.findByText(/seleccione una empresa activa antes de crear empleados/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /crear empleado/i })).toBeDisabled();
  });
});
