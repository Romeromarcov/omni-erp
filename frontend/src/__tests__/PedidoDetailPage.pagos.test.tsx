/**
 * Q1/COV-2 escalón 3: PedidoDetailPage — render de líneas y flujo de pagos,
 * complementa la suite de confirmación (`PedidoDetailPage.test.tsx`). Cubre:
 *  - las columnas del documento (código/cantidad/precio/subtotal con Decimal);
 *  - la info del cliente con RIF y teléfono;
 *  - la lista de pagos registrados;
 *  - Agregar Pago → confirmar: concilia notas, crea pagos, procesa vueltos
 *    y muestra el éxito; y la rama de error;
 *  - cancelar el diálogo de confirmación.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  fetcher: vi.fn(),
}));

const getPagosPedidoMock = vi.fn();
const createPagoDocumentoMock = vi.fn();
const conciliarNotasCreditoMock = vi.fn();
const procesarVueltosMock = vi.fn();
vi.mock('../services/pagosService', () => ({
  pagosService: {
    getPagosPedido: (...a: unknown[]) => getPagosPedidoMock(...a),
    createPagoDocumento: (...a: unknown[]) => createPagoDocumentoMock(...a),
    conciliarNotasCredito: (...a: unknown[]) => conciliarNotasCreditoMock(...a),
    procesarVueltos: (...a: unknown[]) => procesarVueltosMock(...a),
  },
}));

const fetchProductosMock = vi.fn();
vi.mock('../services/productosService', () => ({
  fetchProductos: (...a: unknown[]) => fetchProductosMock(...a),
}));

vi.mock('../services/ventas', () => ({
  pedidoService: { confirmar: vi.fn() },
}));
vi.mock('../services/almacenesService', () => ({
  almacenesService: { getAll: vi.fn().mockResolvedValue([]) },
}));

// ── Stubs de presentación ─────────────────────────────────────────────────────
// LineasProductoTabla se sustituye por una tabla mínima que SÍ invoca los
// `render` de cada columna, para verificar el formateo Decimal del documento.
interface ColumnaStub<T> { key: string; label: string; render: (row: T) => React.ReactNode }
vi.mock('../components/Pedidos/LineasProductoTabla', () => ({
  default: <T,>({ rows, columns, getRowKey }: { rows: T[]; columns: ColumnaStub<T>[]; getRowKey: (r: T) => string }) => (
    <table>
      <tbody>
        {rows.map((row) => (
          <tr key={getRowKey(row)}>
            {columns.map((col) => (
              <td key={col.key}>{col.render(row)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  ),
}));
vi.mock('../components/Pedidos/ResumenTotales', () => ({
  default: () => null,
}));

interface PagoStub {
  monto: number; id_metodo_pago: string; id_moneda: string; tasa: number; referencia?: string;
}
interface NotaStub { id_nota_credito: string; monto_disponible: number }
const PAGO: PagoStub = { monto: 25.5, id_metodo_pago: 'mp-1', id_moneda: 'mon-1', tasa: 1, referencia: 'REF-9' };
const VUELTO: PagoStub = { monto: 1.5, id_metodo_pago: 'mp-1', id_moneda: 'mon-1', tasa: 1 };
const NOTA: NotaStub = { id_nota_credito: 'nc-1', monto_disponible: 4 };

vi.mock('../components/Pedidos/ModalPago', () => ({
  default: ({
    open,
    onConfirm,
  }: {
    open: boolean;
    onConfirm: (pagos: PagoStub[], vueltos?: PagoStub[], notas?: NotaStub[]) => void;
  }) =>
    open ? (
      <button type="button" onClick={() => onConfirm([PAGO], [VUELTO], [NOTA])}>
        stub-confirmar-pago
      </button>
    ) : null,
}));

import { get } from '../services/api';
import PedidoDetailPage from '../pages/Ventas/Pedidos/PedidoDetailPage';

const PEDIDO = {
  id_pedido: 'ped-001',
  numero_pedido: 'P-0001',
  fecha_pedido: '2026-06-01',
  estado: 'APROBADO',
  id_empresa: { id_empresa: 'emp-001', nombre: 'Empresa A' },
  id_sucursal: { id_sucursal: 'suc-1', nombre: 'Sucursal Centro' },
  id_caja: { id_caja: 'caja-1', nombre: 'Caja 1' },
  id_usuario: { id: 1, username: 'cajero', first_name: 'Ana', last_name: 'Pérez' },
  id_cliente: { nombre: 'Juan Pérez', rif: 'V-123', telefono: '0414-1' },
  observaciones: 'Entregar en la tarde',
  detalles: [
    {
      id_detalle_pedido: 'det-1',
      id_producto: { id_producto: 'p1', nombre_producto: 'Producto Uno' },
      cantidad: '2',
      precio_unitario: '12.75',
      subtotal: '25.50',
      observaciones: 'línea con obs',
    },
  ],
};

const PAGO_REGISTRADO = {
  id_pago: 'pg-1',
  metodo_pago_nombre: 'Efectivo',
  moneda_codigo: 'VES',
  monto: '10.00',
  tasa: '1',
  referencia: 'REF-1',
  observaciones: 'pago inicial',
};

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

describe('PedidoDetailPage — líneas y pagos', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockResolvedValue(PEDIDO);
    getPagosPedidoMock.mockResolvedValue([PAGO_REGISTRADO]);
    fetchProductosMock.mockResolvedValue([]);
    createPagoDocumentoMock.mockResolvedValue({});
    conciliarNotasCreditoMock.mockResolvedValue(undefined);
    procesarVueltosMock.mockResolvedValue(undefined);
  });
  afterEach(() => {
    cleanup();
  });

  it('renderiza las líneas con cantidades y montos Decimal a 2 decimales', async () => {
    // La carga del catálogo falla: la página lo tolera (setProductos([])).
    fetchProductosMock.mockRejectedValue(new Error('catálogo caído'));
    renderPage();

    await screen.findByText(/Pedido P-0001/);
    // Columnas: código, producto, cantidad (número), precio y subtotal con D().toFixed(2).
    expect(screen.getByText('p1')).toBeInTheDocument();
    expect(screen.getByText('Producto Uno')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('12.75')).toBeInTheDocument();
    expect(screen.getByText('25.50')).toBeInTheDocument();
    expect(screen.getByText('línea con obs')).toBeInTheDocument();
    // Cliente con RIF y teléfono concatenados.
    expect(screen.getByText('Juan Pérez | RIF: V-123 | Tel: 0414-1')).toBeInTheDocument();
    // Usuario con nombre y apellido.
    expect(screen.getByText('Ana Pérez')).toBeInTheDocument();
    // Pagos registrados.
    expect(screen.getByText(/Efectivo - VES 10\.00 - Tasa: 1/)).toBeInTheDocument();
    expect(screen.getByText('Ref: REF-1')).toBeInTheDocument();
    expect(screen.getByText(/Obs: pago inicial/)).toBeInTheDocument();
  });

  it('Agregar Pago → confirmar: concilia notas, crea el pago, procesa vueltos y muestra éxito', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /agregar pago/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'stub-confirmar-pago' }));

    await waitFor(() => {
      expect(conciliarNotasCreditoMock).toHaveBeenCalledWith([NOTA], 'ped-001', 'PEDIDO');
      expect(createPagoDocumentoMock).toHaveBeenCalledWith(
        'PEDIDO',
        'ped-001',
        expect.objectContaining({ monto: 25.5, id_metodo_pago: 'mp-1', referencia: 'REF-9' }),
      );
      expect(procesarVueltosMock).toHaveBeenCalledWith([VUELTO]);
    });
    expect(await screen.findByText(/Pagos registrados exitosamente/)).toBeInTheDocument();
    // El modal se cierra tras el éxito.
    expect(screen.queryByRole('button', { name: 'stub-confirmar-pago' })).toBeNull();
  });

  it('muestra el error cuando el registro de pagos falla y no procesa vueltos', async () => {
    createPagoDocumentoMock.mockRejectedValue(new Error('500'));
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /agregar pago/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'stub-confirmar-pago' }));

    expect(await screen.findByText(/Error al registrar los pagos/)).toBeInTheDocument();
    expect(procesarVueltosMock).not.toHaveBeenCalled();
  });

  it('permite cancelar el diálogo de confirmación sin confirmar', async () => {
    vi.mocked(get).mockResolvedValue({ ...PEDIDO, estado: 'PENDIENTE' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /confirmar pedido/i }));
    const cancelar = await screen.findByRole('button', { name: /cancelar/i });
    fireEvent.click(cancelar);
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });
});
