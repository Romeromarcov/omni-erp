/**
 * FE-CRIT-1 characterization tests for NotaVentaFormPage.
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

const navigateMock = vi.fn();
let paramsMock: Record<string, string> = {};
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock, useParams: () => paramsMock };
});

// NotaVenta submit goes through NotaVentaService (create→post, update→patch via services/api).
const postMock = vi.fn().mockResolvedValue({ id_nota_venta: 'nv-new', numero_nota_venta: 'NV-1' });
const patchMock = vi.fn().mockResolvedValue({ id_nota_venta: 'nv-1', numero_nota_venta: 'NV-1' });
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

import NotaVentaFormPage from '../pages/Ventas/NotasVenta/NotaVentaFormPage';

const EXISTING_NOTA = {
  id_nota_venta: 'nv-1',
  numero_nota_venta: 'NV-0001',
  fecha_emision: '2026-01-10',
  id_empresa: 'emp-1',
  id_cliente: { id_cliente: 'cli-1' },
  observaciones: 'Observacion nota',
  detalles: [
    { id_producto: 'p1', cantidad: 2, precio_unitario: 10 },
  ],
};

function setGetRouting(editRecord?: unknown) {
  getMock.mockImplementation((url: string) => {
    if (editRecord && url.includes('/ventas/notas-venta/')) return Promise.resolve(editRecord);
    return Promise.resolve([]);
  });
}

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NotaVentaFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('NotaVentaFormPage (characterization)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    paramsMock = {};
    localStorage.clear();
    setGetRouting();
  });

  it('does not call the create mutation on an empty/invalid submit', async () => {
    renderForm();
    const submit = await screen.findByRole('button', { name: /guardar nota de venta/i });
    expect(submit).toBeDisabled();
    expect(postMock).not.toHaveBeenCalled();
  });

  it('loads values when editing an existing nota de venta', async () => {
    paramsMock = { id_nota_venta: 'nv-1' };
    setGetRouting(EXISTING_NOTA);
    renderForm();
    await waitFor(() => {
      expect(screen.getByDisplayValue('Observacion nota')).toBeInTheDocument();
    });
  });

  it('calls the update mutation exactly once with detalles on a valid edit submit', async () => {
    paramsMock = { id_nota_venta: 'nv-1' };
    localStorage.setItem('id_sucursal', 'suc-1');
    setGetRouting(EXISTING_NOTA);
    renderForm();

    const submit = await screen.findByRole('button', { name: /guardar nota de venta/i });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.submit(submit.closest('form')!);

    await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1));
    expect(postMock).not.toHaveBeenCalled();
    const [, payload] = patchMock.mock.calls[0] as [string, Record<string, unknown>];
    expect(Array.isArray(payload.detalles)).toBe(true);
    expect((payload.detalles as unknown[]).length).toBe(1);
  });
});
