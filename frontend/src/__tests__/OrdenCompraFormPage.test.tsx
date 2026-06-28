import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/comprasService', () => ({
  comprasService: {
    getProveedores: vi.fn(),
    crearOrden: vi.fn(),
    crearDetalle: vi.fn(),
  },
}));

vi.mock('../services/productosService', () => ({
  fetchProductos: vi.fn(),
}));

import { comprasService } from '../services/comprasService';
import { fetchProductos } from '../services/productosService';
import OrdenCompraFormPage from '../pages/Compras/OrdenCompraFormPage';

const ordenCreada = {
  id_orden_compra: 'oc-1',
  id_empresa: 'emp-1',
  id_proveedor: 'prov-1',
  tipo_operacion: null,
  fecha_cierre_estimada: null,
  numero_orden: 'OC-0001',
  fecha_orden: '2026-06-12',
  estado: 'BORRADOR',
  observaciones: null,
  activo: true,
  fecha_creacion: '2026-06-12T12:00:00Z',
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/compras/ordenes/nueva']}>
          <Routes>
            <Route path="/compras/ordenes/nueva" element={<OrdenCompraFormPage />} />
            <Route path="/compras/ordenes" element={<div>lista-oc</div>} />
            <Route path="/compras/ordenes/:id" element={<div>detalle-oc</div>} />
          </Routes>
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('OrdenCompraFormPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    vi.mocked(comprasService.getProveedores).mockResolvedValue([
      { id_proveedor: 'prov-1', razon_social: 'ACME C.A.' },
    ]);
    // fetchProductos normaliza la paginación DRF y devuelve un array plano.
    vi.mocked(fetchProductos).mockResolvedValue([
      { id_producto: 'prod-1', nombre_producto: 'Tornillo' },
    ]);
    vi.mocked(comprasService.crearOrden).mockResolvedValue(ordenCreada);
    vi.mocked(comprasService.crearDetalle).mockResolvedValue({
      id_detalle_orden_compra: 'det-1',
      id_orden_compra: 'oc-1',
      id_producto: 'prod-1',
      cantidad: '3',
      precio_unitario: '2.50',
      subtotal: '7.5000',
      observaciones: null,
    });
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  async function completarCabecera(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByLabelText(/proveedor/i));
    await user.click(await screen.findByRole('option', { name: 'ACME C.A.' }));
    await user.type(screen.getByLabelText(/número de orden/i), 'OC-0001');
  }

  it('calcula el subtotal y el total con decimal.js (sin float)', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByLabelText(/proveedor/i);

    await user.type(screen.getAllByLabelText(/cantidad/i)[0], '3');
    await user.type(screen.getAllByLabelText(/precio unitario/i)[0], '0.1');
    // 3 × 0.1 = 0.30 exacto (con float sería 0.30000000000000004).
    expect(await screen.findByText('Total: 0.30')).toBeInTheDocument();
  });

  it('crea la OC y sus líneas con subtotal decimal y navega al detalle', async () => {
    const user = userEvent.setup();
    renderPage();
    await completarCabecera(user);

    await user.click(screen.getAllByLabelText(/producto/i)[0]);
    await user.click(await screen.findByRole('option', { name: 'Tornillo' }));
    await user.type(screen.getAllByLabelText(/cantidad/i)[0], '3');
    await user.type(screen.getAllByLabelText(/precio unitario/i)[0], '2.50');

    await user.click(screen.getByRole('button', { name: /crear orden/i }));

    await waitFor(() => expect(comprasService.crearOrden).toHaveBeenCalled());
    expect(comprasService.crearOrden).toHaveBeenCalledWith(
      expect.objectContaining({ id_proveedor: 'prov-1', numero_orden: 'OC-0001' }),
    );
    expect(comprasService.crearDetalle).toHaveBeenCalledWith({
      id_orden_compra: 'oc-1',
      id_producto: 'prod-1',
      cantidad: '3',
      precio_unitario: '2.50',
      subtotal: '7.5000',
    });
    expect(await screen.findByText('detalle-oc')).toBeInTheDocument();
  });

  it('valida con zod los campos obligatorios sin llamar al backend', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByLabelText(/proveedor/i);
    await user.click(screen.getByRole('button', { name: /crear orden/i }));
    expect(await screen.findByText('El proveedor es obligatorio')).toBeInTheDocument();
    expect(screen.getByText('El número de orden es obligatorio')).toBeInTheDocument();
    expect(comprasService.crearOrden).not.toHaveBeenCalled();
  });

  it('agrega y quita líneas', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByLabelText(/proveedor/i);
    await user.click(screen.getByRole('button', { name: /agregar línea/i }));
    expect(screen.getAllByLabelText(/precio unitario/i)).toHaveLength(2);
    await user.click(screen.getAllByRole('button', { name: /quitar línea/i })[1]);
    expect(screen.getAllByLabelText(/precio unitario/i)).toHaveLength(1);
  });

  it('muestra el 400 del backend (p. ej. número de orden duplicado)', async () => {
    const user = userEvent.setup();
    vi.mocked(comprasService.crearOrden).mockRejectedValue(
      new Error(JSON.stringify({ non_field_errors: ['Ya existe una orden con ese número.'] })),
    );
    renderPage();
    await completarCabecera(user);
    await user.click(screen.getAllByLabelText(/producto/i)[0]);
    await user.click(await screen.findByRole('option', { name: 'Tornillo' }));
    await user.type(screen.getAllByLabelText(/cantidad/i)[0], '1');
    await user.type(screen.getAllByLabelText(/precio unitario/i)[0], '1');
    await user.click(screen.getByRole('button', { name: /crear orden/i }));
    expect(await screen.findByText('Ya existe una orden con ese número.')).toBeInTheDocument();
  });
});
