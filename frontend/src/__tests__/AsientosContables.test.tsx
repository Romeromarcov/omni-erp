import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/contabilidadService', () => ({
  contabilidadService: {
    getAsientosPaginated: vi.fn(),
    getAsiento: vi.fn(),
    getPlanCuentas: vi.fn(),
  },
}));

import { contabilidadService } from '../services/contabilidadService';
import AsientosContablesListPage from '../pages/Contabilidad/AsientosContablesListPage';
import AsientoContableDetailPage from '../pages/Contabilidad/AsientoContableDetailPage';

const asiento = {
  id_asiento: 'as-1',
  id_empresa: 'emp-1',
  fecha_asiento: '2026-06-10',
  numero_asiento: 'AS-0001',
  descripcion: 'Cambio de divisas',
  id_documento_origen: null,
  nombre_modelo_origen: 'OperacionCambioDivisa',
  estado_asiento: 'APROBADO',
  fecha_creacion: '2026-06-10T10:00:00Z',
  detalles: [
    {
      id_detalle_asiento: 'det-1',
      id_asiento: 'as-1',
      id_cuenta_contable: 'cta-1',
      debe: '100.10',
      haber: '0.00',
      descripcion_detalle: 'Debe divisa',
      fecha_creacion: '2026-06-10T10:00:00Z',
    },
    {
      id_detalle_asiento: 'det-2',
      id_asiento: 'as-1',
      id_cuenta_contable: 'cta-2',
      debe: '0.00',
      haber: '100.10',
      descripcion_detalle: 'Haber divisa',
      fecha_creacion: '2026-06-10T10:00:00Z',
    },
  ],
};

const planCuentas = [
  {
    id_cuenta_contable: 'cta-1',
    id_empresa: 'emp-1',
    codigo_cuenta: '1.1',
    nombre_cuenta: 'Bancos',
    tipo_cuenta: 'ACTIVO',
    naturaleza: 'DEUDORA',
    id_cuenta_padre: null,
    nivel: 2,
    activo: true,
    fecha_creacion: '2026-06-01T10:00:00Z',
  },
];

function renderList() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/contabilidad/asientos']}>
        <AsientosContablesListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderDetail(id = 'as-1') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/contabilidad/asientos/${id}`]}>
        <Routes>
          <Route path="/contabilidad/asientos/:id" element={<AsientoContableDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AsientosContablesListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(contabilidadService.getAsientosPaginated).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [asiento],
    });
  });

  afterEach(() => cleanup());

  it('lista los asientos con número, fecha, origen y estado', async () => {
    renderList();
    expect(await screen.findByText('AS-0001')).toBeInTheDocument();
    expect(screen.getByText('2026-06-10')).toBeInTheDocument();
    expect(screen.getByText('OperacionCambioDivisa')).toBeInTheDocument();
    expect(screen.getByText('APROBADO')).toBeInTheDocument();
  });

  it('aplica el filtro por estado y reinicia la página', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('AS-0001');

    await user.click(screen.getByLabelText(/Estado/));
    await user.click(await screen.findByRole('option', { name: 'BORRADOR' }));

    await waitFor(() => {
      expect(contabilidadService.getAsientosPaginated).toHaveBeenCalledWith(1, 20, {
        estado: 'BORRADOR',
        fechaDesde: '',
        fechaHasta: '',
      });
    });
  });

  it('aplica el filtro por rango de fechas', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('AS-0001');

    await user.type(screen.getByLabelText(/Desde/), '2026-06-01');
    await user.type(screen.getByLabelText(/Hasta/), '2026-06-30');

    await waitFor(() => {
      expect(contabilidadService.getAsientosPaginated).toHaveBeenCalledWith(1, 20, {
        estado: '',
        fechaDesde: '2026-06-01',
        fechaHasta: '2026-06-30',
      });
    });
  });
});

describe('AsientoContableDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(contabilidadService.getAsiento).mockResolvedValue(asiento);
    vi.mocked(contabilidadService.getPlanCuentas).mockResolvedValue(planCuentas);
  });

  afterEach(() => cleanup());

  it('muestra las líneas con totales decimal.js EXACTOS y chip Cuadrado', async () => {
    renderDetail();
    expect(await screen.findByText(/Asiento AS-0001/)).toBeInTheDocument();
    // 100.10 en debe línea 1 y haber línea 2 + ambos totales.
    expect(screen.getAllByText('100.10')).toHaveLength(4);
    expect(screen.getByText('1.1 — Bancos')).toBeInTheDocument(); // cuenta resuelta del plan
    expect(screen.getByText('cta-2')).toBeInTheDocument(); // cuenta sin nombre conocido
    expect(screen.getByText('Cuadrado')).toBeInTheDocument();
    expect(screen.queryByText('Descuadrado')).not.toBeInTheDocument();
  });

  it('marca Descuadrado y muestra la diferencia exacta cuando debe ≠ haber', async () => {
    vi.mocked(contabilidadService.getAsiento).mockResolvedValue({
      ...asiento,
      detalles: [
        { ...asiento.detalles[0], debe: '0.30' },
        { ...asiento.detalles[1], haber: '0.10' },
      ],
    });
    renderDetail();
    expect(await screen.findByText('Descuadrado')).toBeInTheDocument();
    // 0.30 − 0.10 = 0.20 exacto (con float sería 0.19999999999999998).
    expect(screen.getByText(/diferencia Debe − Haber = 0\.20/)).toBeInTheDocument();
  });

  it('muestra el error si el asiento no carga', async () => {
    vi.mocked(contabilidadService.getAsiento).mockRejectedValue(
      new Error(JSON.stringify({ detail: 'No encontrado.' })),
    );
    renderDetail();
    expect(await screen.findByText('No encontrado.')).toBeInTheDocument();
  });
});
