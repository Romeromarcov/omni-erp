import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  fetcher: vi.fn(),
}));

vi.mock('../services/pagosService', () => ({
  pagosService: {
    getPagosPedido: vi.fn().mockResolvedValue([]),
    createPagoDocumento: vi.fn(),
    conciliarNotasCredito: vi.fn(),
    procesarVueltos: vi.fn(),
  },
}));

vi.mock('../services/productosService', () => ({
  fetchProductos: vi.fn().mockResolvedValue([]),
}));

vi.mock('../services/ventas', () => ({
  pedidoService: {
    confirmar: vi.fn(),
  },
}));

vi.mock('../services/almacenesService', () => ({
  almacenesService: {
    getAll: vi.fn(),
  },
}));

vi.mock('../components/Pedidos/ModalPago', () => ({
  default: () => null,
}));

import { get } from '../services/api';
import { pedidoService } from '../services/ventas';
import { almacenesService } from '../services/almacenesService';
import PedidoDetailPage from '../pages/Ventas/Pedidos/PedidoDetailPage';

const mockPedido = {
  id_pedido: 'ped-001',
  numero_pedido: 'P-0001',
  fecha_pedido: '2026-06-01',
  estado: 'PENDIENTE',
  id_empresa: { id_empresa: 'emp-001', nombre: 'Empresa A' },
  id_cliente: { nombre: 'Juan Pérez' },
  detalles: [],
};

const mockAlmacenes = [
  { id_almacen: 'alm-001', nombre_almacen: 'Almacén Central', id_empresa: 'emp-001' },
  { id_almacen: 'alm-002', nombre_almacen: 'Almacén Otra Empresa', id_empresa: 'emp-999' },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/ventas/pedidos/ped-001']}>
        <FeedbackProvider>
          <Routes>
            <Route path="/ventas/pedidos/:id_pedido" element={<PedidoDetailPage />} />
          </Routes>
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('PedidoDetailPage — confirmar pedido', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockResolvedValue(mockPedido);
    vi.mocked(almacenesService.getAll).mockResolvedValue(mockAlmacenes);
  });

  afterEach(() => {
    cleanup();
  });

  it('muestra el botón "Confirmar pedido" para pedidos PENDIENTE', async () => {
    renderPage();
    expect(await screen.findByRole('button', { name: /confirmar pedido/i })).toBeInTheDocument();
  });

  it('no muestra el botón para pedidos APROBADOS', async () => {
    vi.mocked(get).mockResolvedValue({ ...mockPedido, estado: 'APROBADO' });
    renderPage();
    await screen.findByText(/Pedido P-0001/);
    expect(screen.queryByRole('button', { name: /confirmar pedido/i })).not.toBeInTheDocument();
  });

  it('confirma con el almacén seleccionado (solo almacenes de la empresa del pedido)', async () => {
    vi.mocked(pedidoService.confirmar).mockResolvedValue({
      pedido_id: 'ped-001',
      numero_pedido: 'P-0001',
      estado: 'APROBADO',
      reservas_creadas: 2,
      cxc_generada: true,
      cxc_id: 'cxc-1',
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /confirmar pedido/i }));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByLabelText(/almacén de despacho/i));
    const listbox = await screen.findByRole('listbox');
    // El almacén de otra empresa no se ofrece
    expect(within(listbox).queryByText('Almacén Otra Empresa')).not.toBeInTheDocument();
    await user.click(within(listbox).getByText('Almacén Central'));

    await user.click(within(dialog).getByRole('button', { name: /^confirmar$/i }));
    await waitFor(() => {
      expect(pedidoService.confirmar).toHaveBeenCalledWith('ped-001', 'alm-001');
    });
    // feedback de éxito (snackbar)
    expect(await screen.findByText(/confirmado/i)).toBeInTheDocument();
  });

  it('muestra el error 400 del backend en el diálogo', async () => {
    vi.mocked(pedidoService.confirmar).mockRejectedValue(
      new Error(JSON.stringify(['Stock insuficiente para Producto A']))
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /confirmar pedido/i }));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByLabelText(/almacén de despacho/i));
    await user.click(within(await screen.findByRole('listbox')).getByText('Almacén Central'));
    await user.click(within(dialog).getByRole('button', { name: /^confirmar$/i }));

    expect(await screen.findByText(/stock insuficiente/i)).toBeInTheDocument();
  });
});
