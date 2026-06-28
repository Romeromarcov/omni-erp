import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/comprasService', () => ({
  comprasService: {
    getOrden: vi.fn(),
    getDetallesOrden: vi.fn(),
    getRecepcionesOrden: vi.fn(),
    aprobarOrden: vi.fn(),
    recepcionar: vi.fn(),
    facturar: vi.fn(),
  },
}));

vi.mock('../services/almacenesService', () => ({
  almacenesService: {
    getAll: vi.fn(),
  },
}));

vi.mock('../services/productosService', () => ({
  fetchProductos: vi.fn(),
}));

import { comprasService } from '../services/comprasService';
import { almacenesService } from '../services/almacenesService';
import { fetchProductos } from '../services/productosService';
import OrdenCompraDetailPage from '../pages/Compras/OrdenCompraDetailPage';

const orden = {
  id_orden_compra: 'oc-1',
  id_empresa: 'emp-1',
  id_proveedor: 'prov-1',
  tipo_operacion: null,
  fecha_cierre_estimada: null,
  numero_orden: 'OC-0001',
  fecha_orden: '2026-06-10',
  estado: 'APROBADA',
  observaciones: null,
  activo: true,
  fecha_creacion: '2026-06-10T12:00:00Z',
};

const detalles = [
  {
    id_detalle_orden_compra: 'det-1',
    id_orden_compra: 'oc-1',
    id_producto: 'prod-1',
    cantidad: '10.0000',
    precio_unitario: '25.5000',
    subtotal: '255.0000',
    observaciones: null,
  },
  {
    id_detalle_orden_compra: 'det-2',
    id_orden_compra: 'oc-1',
    id_producto: 'prod-2',
    cantidad: '2.0000',
    precio_unitario: '0.1000',
    subtotal: '0.2000',
    observaciones: null,
  },
];

const recepcion = {
  id_recepcion: 'rec-1',
  id_empresa: 'emp-1',
  id_orden_compra: 'oc-1',
  fecha_recepcion: '2026-06-11',
  monto_total: '255.2000',
  observaciones: null,
  activo: true,
  fecha_creacion: '2026-06-11T10:00:00Z',
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/compras/ordenes/oc-1']}>
          <Routes>
            <Route path="/compras/ordenes/:id" element={<OrdenCompraDetailPage />} />
            <Route path="/compras/ordenes" element={<div>lista-oc</div>} />
          </Routes>
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('OrdenCompraDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    vi.mocked(comprasService.getOrden).mockResolvedValue(orden);
    vi.mocked(comprasService.getDetallesOrden).mockResolvedValue(detalles);
    vi.mocked(comprasService.getRecepcionesOrden).mockResolvedValue([]);
    vi.mocked(almacenesService.getAll).mockResolvedValue([
      { id_almacen: 'alm-1', nombre_almacen: 'Principal', id_empresa: 'emp-1' },
    ]);
    vi.mocked(fetchProductos).mockResolvedValue([
      { id_producto: 'prod-1', nombre_producto: 'Tornillo' },
      { id_producto: 'prod-2', nombre_producto: 'Tuerca' },
    ]);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('muestra las líneas con nombre de producto y el total Decimal', async () => {
    renderPage();
    expect(await screen.findByText('Tornillo')).toBeInTheDocument();
    expect(screen.getByText('Tuerca')).toBeInTheDocument();
    expect(screen.getByText('255.00')).toBeInTheDocument();
    // 255.0000 + 0.2000 sumado con decimal.js → 255.20 exacto.
    expect(screen.getByText('Total: 255.20')).toBeInTheDocument();
    expect(screen.getByText('APROBADA')).toBeInTheDocument();
  });

  it('deshabilita Aprobar si la OC ya está aprobada y la aprueba si es borrador', async () => {
    vi.mocked(comprasService.getOrden).mockResolvedValue({ ...orden, estado: 'BORRADOR' });
    vi.mocked(comprasService.aprobarOrden).mockResolvedValue({
      detail: 'Orden aprobada.',
      estado: 'APROBADA',
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Tornillo');
    await user.click(screen.getByRole('button', { name: /^aprobar$/i }));
    await waitFor(() => expect(comprasService.aprobarOrden).toHaveBeenCalledWith('oc-1'));
  });

  it('recepciona la mercancía con items prellenados desde las líneas', async () => {
    vi.mocked(comprasService.recepcionar).mockResolvedValue({
      recepcion_id: 'rec-1',
      movimientos: 2,
      cxp_id: 'cxp-1',
      monto_total: '255.2000',
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Tornillo');

    await user.click(screen.getByRole('button', { name: /recepcionar mercancía/i }));
    await user.click(await screen.findByLabelText(/almacén/i));
    await user.click(await screen.findByRole('option', { name: 'Principal' }));
    await user.click(screen.getByRole('button', { name: /registrar recepción/i }));

    await waitFor(() =>
      expect(comprasService.recepcionar).toHaveBeenCalledWith({
        orden_compra_id: 'oc-1',
        almacen_id: 'alm-1',
        items: [
          { producto_id: 'prod-1', cantidad: '10.0000', costo_unitario: '25.5000' },
          { producto_id: 'prod-2', cantidad: '2.0000', costo_unitario: '0.1000' },
        ],
      }),
    );
  });

  it('muestra el 400 del backend al recepcionar (p. ej. falta mapeo contable)', async () => {
    vi.mocked(comprasService.recepcionar).mockRejectedValue(
      new Error(
        JSON.stringify({ detail: 'No hay mapeo contable INVENTARIO configurado para la empresa.' }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Tornillo');
    await user.click(screen.getByRole('button', { name: /recepcionar mercancía/i }));
    await user.click(await screen.findByLabelText(/almacén/i));
    await user.click(await screen.findByRole('option', { name: 'Principal' }));
    await user.click(screen.getByRole('button', { name: /registrar recepción/i }));
    expect(
      await screen.findByText('No hay mapeo contable INVENTARIO configurado para la empresa.'),
    ).toBeInTheDocument();
  });

  it('registra la factura sobre una recepción existente', async () => {
    vi.mocked(comprasService.getRecepcionesOrden).mockResolvedValue([recepcion]);
    vi.mocked(comprasService.facturar).mockResolvedValue({
      factura_id: 'fac-1',
      numero_factura: 'FAC-001',
      monto_total: '255.2000',
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Tornillo');

    await user.click(screen.getByRole('button', { name: /^registrar factura$/i }));
    await user.type(await screen.findByLabelText(/número de factura/i), 'FAC-001');
    const confirmar = screen
      .getAllByRole('button', { name: /registrar factura/i })
      .find((b) => b.getAttribute('type') === 'submit')!;
    await user.click(confirmar);

    await waitFor(() =>
      expect(comprasService.facturar).toHaveBeenCalledWith({
        recepcion_id: 'rec-1',
        numero_factura: 'FAC-001',
      }),
    );
  });

  it('muestra el 400 del backend al facturar (número duplicado)', async () => {
    vi.mocked(comprasService.getRecepcionesOrden).mockResolvedValue([recepcion]);
    vi.mocked(comprasService.facturar).mockRejectedValue(
      new Error(JSON.stringify({ detail: 'Ya existe una factura con ese número.' })),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Tornillo');
    await user.click(screen.getByRole('button', { name: /^registrar factura$/i }));
    await user.type(await screen.findByLabelText(/número de factura/i), 'FAC-001');
    const confirmar = screen
      .getAllByRole('button', { name: /registrar factura/i })
      .find((b) => b.getAttribute('type') === 'submit')!;
    await user.click(confirmar);
    expect(await screen.findByText('Ya existe una factura con ese número.')).toBeInTheDocument();
  });

  it('bloquea facturar sin recepciones registradas', async () => {
    renderPage();
    await screen.findByText('Tornillo');
    expect(screen.getByRole('button', { name: /^registrar factura$/i })).toBeDisabled();
    expect(screen.getByText(/no tiene recepciones registradas/i)).toBeInTheDocument();
  });
});
