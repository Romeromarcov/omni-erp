import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/contabilidadService', () => ({
  contabilidadService: {
    getMapeos: vi.fn(),
    getTiposAsiento: vi.fn(),
    getPlanCuentas: vi.fn(),
    crearMapeo: vi.fn(),
    actualizarMapeo: vi.fn(),
  },
}));

import { contabilidadService } from '../services/contabilidadService';
import MapeosContablesPage from '../pages/Contabilidad/MapeosContablesPage';

const tipos = [
  { value: 'FACTURA_VENTA', label: 'Factura de Venta' },
  { value: 'CAMBIO_DIVISA', label: 'Cambio de Divisa' },
];

const mapeo = {
  id_mapeo: 'map-1',
  id_empresa: 'emp-1',
  tipo_asiento: 'FACTURA_VENTA',
  tipo_asiento_display: 'Factura de Venta',
  cuenta_debe: 'cta-1',
  cuenta_debe_nombre: 'Cuentas por Cobrar',
  cuenta_haber: 'cta-2',
  cuenta_haber_nombre: 'Ingresos por Ventas',
  descripcion_plantilla: '{tipo} - {numero}',
  activo: true,
  fecha_creacion: '2026-06-01T10:00:00Z',
};

const cuentas = [
  {
    id_cuenta_contable: 'cta-1',
    id_empresa: 'emp-1',
    codigo_cuenta: '1.2',
    nombre_cuenta: 'Cuentas por Cobrar',
    tipo_cuenta: 'ACTIVO',
    naturaleza: 'DEUDORA',
    id_cuenta_padre: null,
    nivel: 2,
    activo: true,
    fecha_creacion: '2026-06-01T10:00:00Z',
  },
  {
    id_cuenta_contable: 'cta-2',
    id_empresa: 'emp-1',
    codigo_cuenta: '4.1',
    nombre_cuenta: 'Ingresos por Ventas',
    tipo_cuenta: 'INGRESO',
    naturaleza: 'ACREEDORA',
    id_cuenta_padre: null,
    nivel: 2,
    activo: true,
    fecha_creacion: '2026-06-01T10:00:00Z',
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/contabilidad/mapeos']}>
          <MapeosContablesPage />
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('MapeosContablesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    vi.mocked(contabilidadService.getMapeos).mockResolvedValue([mapeo]);
    vi.mocked(contabilidadService.getTiposAsiento).mockResolvedValue(tipos);
    vi.mocked(contabilidadService.getPlanCuentas).mockResolvedValue(cuentas);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('lista los mapeos y alerta los tipos SIN mapeo (los que dan 422)', async () => {
    renderPage();
    expect(await screen.findByText('Factura de Venta')).toBeInTheDocument();
    expect(screen.getByText('Cuentas por Cobrar')).toBeInTheDocument();
    expect(screen.getByText('Ingresos por Ventas')).toBeInTheDocument();
    // CAMBIO_DIVISA no tiene mapeo → aparece en la alerta de faltantes.
    expect(screen.getByText(/Cambio de Divisa/)).toBeInTheDocument();
    expect(screen.getByText(/fallarán con 422/)).toBeInTheDocument();
  });

  it('crea un mapeo solo para tipos disponibles (sin duplicar unique empresa+tipo)', async () => {
    vi.mocked(contabilidadService.crearMapeo).mockResolvedValue({
      ...mapeo,
      id_mapeo: 'map-2',
      tipo_asiento: 'CAMBIO_DIVISA',
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Factura de Venta');

    await user.click(screen.getByRole('button', { name: 'Nuevo mapeo' }));
    await user.click(screen.getByLabelText(/Tipo de asiento/));
    // FACTURA_VENTA ya está mapeado: la única opción elegible es CAMBIO_DIVISA.
    expect(screen.queryByRole('option', { name: 'Factura de Venta' })).not.toBeInTheDocument();
    await user.click(await screen.findByRole('option', { name: 'Cambio de Divisa' }));

    await user.click(screen.getByLabelText(/Cuenta Debe/));
    await user.click(await screen.findByRole('option', { name: /1\.2 — Cuentas por Cobrar/ }));
    await user.click(screen.getByLabelText(/Cuenta Haber/));
    await user.click(await screen.findByRole('option', { name: /4\.1 — Ingresos por Ventas/ }));

    await user.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(contabilidadService.crearMapeo).toHaveBeenCalledWith({
        id_empresa: 'emp-1',
        tipo_asiento: 'CAMBIO_DIVISA',
        cuenta_debe: 'cta-1',
        cuenta_haber: 'cta-2',
        descripcion_plantilla: '{tipo} - {numero}',
      });
    });
  });

  it('edita un mapeo existente con PATCH (sin tocar el tipo)', async () => {
    vi.mocked(contabilidadService.actualizarMapeo).mockResolvedValue(mapeo);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Factura de Venta');

    await user.click(screen.getByRole('button', { name: 'Editar' }));
    await user.click(screen.getByLabelText(/Cuenta Haber/));
    await user.click(await screen.findByRole('option', { name: /1\.2 — Cuentas por Cobrar/ }));
    await user.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(contabilidadService.actualizarMapeo).toHaveBeenCalledWith('map-1', {
        cuenta_debe: 'cta-1',
        cuenta_haber: 'cta-1',
        descripcion_plantilla: '{tipo} - {numero}',
      });
    });
  });

  it('muestra el error del backend al guardar', async () => {
    vi.mocked(contabilidadService.crearMapeo).mockRejectedValue(
      new Error(JSON.stringify({ cuenta_debe: ['La cuenta no pertenece a la empresa del mapeo.'] })),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Factura de Venta');

    await user.click(screen.getByRole('button', { name: 'Nuevo mapeo' }));
    await user.click(screen.getByLabelText(/Tipo de asiento/));
    await user.click(await screen.findByRole('option', { name: 'Cambio de Divisa' }));
    await user.click(screen.getByLabelText(/Cuenta Debe/));
    await user.click(await screen.findByRole('option', { name: /1\.2 — Cuentas por Cobrar/ }));
    await user.click(screen.getByLabelText(/Cuenta Haber/));
    await user.click(await screen.findByRole('option', { name: /4\.1 — Ingresos por Ventas/ }));
    await user.click(screen.getByRole('button', { name: 'Guardar' }));

    expect(
      await screen.findByText(/La cuenta no pertenece a la empresa del mapeo\./),
    ).toBeInTheDocument();
  });
});
