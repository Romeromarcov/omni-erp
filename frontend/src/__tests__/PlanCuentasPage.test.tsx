import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/contabilidadService', () => ({
  contabilidadService: {
    getPlanCuentas: vi.fn(),
    crearCuenta: vi.fn(),
  },
}));

import { contabilidadService } from '../services/contabilidadService';
import PlanCuentasPage from '../pages/Contabilidad/PlanCuentasPage';

const cuentaRaiz = {
  id_cuenta_contable: 'cta-1',
  id_empresa: 'emp-1',
  codigo_cuenta: '1',
  nombre_cuenta: 'Activo',
  tipo_cuenta: 'ACTIVO',
  naturaleza: 'DEUDORA',
  id_cuenta_padre: null,
  nivel: 1,
  activo: true,
  fecha_creacion: '2026-06-01T10:00:00Z',
};

const cuentaHija = {
  ...cuentaRaiz,
  id_cuenta_contable: 'cta-2',
  codigo_cuenta: '1.1',
  nombre_cuenta: 'Bancos',
  id_cuenta_padre: 'cta-1',
  nivel: 2,
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/contabilidad/plan-cuentas']}>
          <PlanCuentasPage />
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('PlanCuentasPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    // Desordenadas a propósito: la página ordena por código.
    vi.mocked(contabilidadService.getPlanCuentas).mockResolvedValue([cuentaHija, cuentaRaiz]);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('lista las cuentas ordenadas por código con su nivel', async () => {
    renderPage();
    expect(await screen.findByText('Activo')).toBeInTheDocument();
    expect(screen.getByText('Bancos')).toBeInTheDocument();
    const filas = screen.getAllByRole('row').slice(1); // sin cabecera
    // Ordenadas por código: la raíz '1' (Activo) antes que '1.1' (Bancos).
    expect(within(filas[0]).getByText('Activo')).toBeInTheDocument();
    expect(within(filas[1]).getByText('Bancos')).toBeInTheDocument();
    expect(within(filas[1]).getByText('1.1')).toBeInTheDocument();
  });

  it('crea una cuenta hija derivando el nivel del padre (padre.nivel + 1)', async () => {
    vi.mocked(contabilidadService.crearCuenta).mockResolvedValue({
      ...cuentaHija,
      id_cuenta_contable: 'cta-3',
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Activo');

    await user.click(screen.getByRole('button', { name: 'Nueva cuenta' }));
    await user.type(screen.getByLabelText(/Código/), '1.2');
    await user.type(screen.getByLabelText(/^Nombre/), 'Caja chica');

    await user.click(screen.getByLabelText(/Tipo/));
    await user.click(await screen.findByRole('option', { name: 'ACTIVO' }));
    await user.click(screen.getByLabelText(/Naturaleza/));
    await user.click(await screen.findByRole('option', { name: 'DEUDORA' }));
    await user.click(screen.getByLabelText(/Cuenta padre/));
    await user.click(await screen.findByRole('option', { name: /1 — Activo/ }));

    await user.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(contabilidadService.crearCuenta).toHaveBeenCalledWith({
        id_empresa: 'emp-1',
        codigo_cuenta: '1.2',
        nombre_cuenta: 'Caja chica',
        tipo_cuenta: 'ACTIVO',
        naturaleza: 'DEUDORA',
        id_cuenta_padre: 'cta-1',
        nivel: 2,
      });
    });
  });

  it('muestra el error del backend si la creación falla', async () => {
    vi.mocked(contabilidadService.crearCuenta).mockRejectedValue(
      new Error(JSON.stringify({ codigo_cuenta: ['Ya existe una cuenta con este código.'] })),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Activo');

    await user.click(screen.getByRole('button', { name: 'Nueva cuenta' }));
    await user.type(screen.getByLabelText(/Código/), '1');
    await user.type(screen.getByLabelText(/^Nombre/), 'Duplicada');
    await user.click(screen.getByLabelText(/Tipo/));
    await user.click(await screen.findByRole('option', { name: 'ACTIVO' }));
    await user.click(screen.getByLabelText(/Naturaleza/));
    await user.click(await screen.findByRole('option', { name: 'DEUDORA' }));
    await user.click(screen.getByRole('button', { name: 'Guardar' }));

    expect(
      await screen.findByText(/Ya existe una cuenta con este código\./),
    ).toBeInTheDocument();
  });

  it('valida campos obligatorios sin llamar al servicio', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Activo');
    await user.click(screen.getByRole('button', { name: 'Nueva cuenta' }));
    await user.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText('El código es obligatorio')).toBeInTheDocument();
    expect(contabilidadService.crearCuenta).not.toHaveBeenCalled();
  });
});
