/**
 * FE-CRIT-1 characterization tests for CotizacionFormPage.
 * Captures CURRENT behavior before/after the react-hook-form migration:
 *  (a) empty/invalid submit does NOT call the create mutation;
 *  (b) editing an existing record loads its values into the form;
 *  (c) a valid (edit-loaded) submit calls the update mutation exactly once
 *      with the expected payload shape.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

const navigateMock = vi.fn();
let paramsMock: Record<string, string> = {};
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock, useParams: () => paramsMock };
});

// ── Network layer (services/api) ─────────────────────────────────────────────
const postMock = vi.fn().mockResolvedValue({ id_cotizacion: 'cot-new', numero_cotizacion: 'COT-1' });
const patchMock = vi.fn().mockResolvedValue({ id_cotizacion: 'cot-1', numero_cotizacion: 'COT-1' });
const getMock = vi.fn();
vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return {
    ...actual,
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    patch: (...a: unknown[]) => patchMock(...a),
  };
});

// Cotizacion submit goes through cotizacionService.create/update.
vi.mock('../services/ventas', () => ({
  cotizacionService: {
    create: (...a: unknown[]) => postMock(...a),
    update: (...a: unknown[]) => patchMock(...a),
  },
}));

// ── Side-effect services invoked by useDocumentoVentaBase ────────────────────
vi.mock('../services/productosService', () => ({
  fetchProductos: vi.fn().mockResolvedValue([
    { id_producto: 'p1', nombre_producto: 'Producto Uno', sku: 'SKU1', precio_venta_sugerido: 10 },
  ]),
}));
vi.mock('../services/clientesService', () => ({
  buscarClientes: vi.fn().mockResolvedValue([]),
  buscarClientesSimilares: vi.fn().mockResolvedValue([]),
  crearClienteConEmpresa: vi.fn().mockResolvedValue({ id_cliente: 'c-auto' }),
}));
vi.mock('../services/users', () => ({
  fetchUsuarios: vi.fn().mockResolvedValue([]),
}));
vi.mock('../services/sesionService', () => ({
  getSesionActiva: vi.fn().mockResolvedValue(null),
}));
vi.mock('../services/pagosService', () => ({
  pagosService: {
    createPagoDocumento: vi.fn().mockResolvedValue({}),
    procesarVueltos: vi.fn().mockResolvedValue(undefined),
    conciliarNotasCredito: vi.fn().mockResolvedValue(undefined),
  },
}));

import CotizacionFormPage from '../pages/Ventas/Cotizaciones/CotizacionFormPage';

const EXISTING_COTIZACION = {
  id_cotizacion: 'cot-1',
  numero_cotizacion: 'COT-0001',
  fecha_cotizacion: '2026-01-10',
  fecha_vencimiento: '2026-02-10',
  estado: 'BORRADOR',
  id_empresa: 'emp-1',
  id_cliente: { id_cliente: 'cli-1' },
  id_moneda: 'mon-1',
  observaciones: 'Observacion existente',
  condiciones_comerciales: 'Pago a 30 dias',
  detalles: [
    { id_producto: 'p1', cantidad: 2, precio_unitario: 10, descuento_porcentaje: 0, sku: 'SKU1', producto: 'Producto Uno' },
  ],
};

function setGetRouting(editRecord?: unknown) {
  getMock.mockImplementation((url: string) => {
    if (editRecord && url.includes('/ventas/cotizaciones/')) return Promise.resolve(editRecord);
    return Promise.resolve([]); // cajas-usuario, sucursales, empresas, etc.
  });
}

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FeedbackProvider>
          <CotizacionFormPage />
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CotizacionFormPage (characterization)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    paramsMock = {};
    localStorage.clear();
    setGetRouting();
  });

  it('does not call the create mutation on an empty/invalid submit', async () => {
    renderForm();
    const submit = await screen.findByRole('button', { name: /guardar cotización/i });
    // Sin cliente seleccionado el guardado está bloqueado.
    expect(submit).toBeDisabled();
    expect(postMock).not.toHaveBeenCalled();
  });

  it('loads values when editing an existing cotización', async () => {
    paramsMock = { id: 'cot-1' };
    setGetRouting(EXISTING_COTIZACION);
    renderForm();
    await waitFor(() => {
      expect(screen.getByDisplayValue('Observacion existente')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Pago a 30 dias')).toBeInTheDocument();
    });
  });

  it('calls the update mutation exactly once with detalles on a valid edit submit', async () => {
    paramsMock = { id: 'cot-1' };
    localStorage.setItem('id_sucursal', 'suc-1');
    setGetRouting(EXISTING_COTIZACION);
    renderForm();

    const submit = await screen.findByRole('button', { name: /guardar cotización/i });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.submit(submit.closest('form')!);
    await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1));
    expect(postMock).not.toHaveBeenCalled();
    const [, payload] = patchMock.mock.calls[0] as [string, Record<string, unknown>];
    expect(Array.isArray(payload.detalles)).toBe(true);
    expect((payload.detalles as unknown[]).length).toBe(1);
  });
});
