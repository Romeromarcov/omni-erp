/**
 * Q1/COV-2 escalón 2: tests de los hooks de formularios de documentos de venta
 * (useCotizacionForm / usePedidoForm / useNotaVentaForm). Cubre las ramas de
 * submit que las pruebas de página no ejercitan: creación con pagos, error
 * parcial de pagos, autocreación de cliente fallida, actualización (edición) y
 * error del servicio.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { Pago } from '../components/Pedidos/types';
import type {
  CotizacionFormInput,
  PedidoFormInput,
  NotaVentaFormInput,
} from '../schemas/ventas.schemas';

// ── Mocks de red y servicios ──────────────────────────────────────────────────
const getMock = vi.fn();
const postMock = vi.fn();
const patchMock = vi.fn();
vi.mock('../services/api', () => ({
  get: (...a: unknown[]) => getMock(...a),
  post: (...a: unknown[]) => postMock(...a),
  patch: (...a: unknown[]) => patchMock(...a),
}));

const cotizacionCreateMock = vi.fn();
const cotizacionUpdateMock = vi.fn();
const notaVentaCreateMock = vi.fn();
const notaVentaUpdateMock = vi.fn();
vi.mock('../services/ventas', () => ({
  cotizacionService: {
    create: (...a: unknown[]) => cotizacionCreateMock(...a),
    update: (...a: unknown[]) => cotizacionUpdateMock(...a),
  },
  NotaVentaService: class {
    create(...a: unknown[]) { return notaVentaCreateMock(...a); }
    update(...a: unknown[]) { return notaVentaUpdateMock(...a); }
  },
}));

const createPagoDocumentoMock = vi.fn();
vi.mock('../services/pagosService', () => ({
  pagosService: {
    createPagoDocumento: (...a: unknown[]) => createPagoDocumentoMock(...a),
  },
}));

const crearClienteConEmpresaMock = vi.fn();
vi.mock('../services/clientesService', () => ({
  buscarClientes: vi.fn().mockResolvedValue([]),
  buscarClientesSimilares: vi.fn().mockResolvedValue([]),
  crearClienteConEmpresa: (...a: unknown[]) => crearClienteConEmpresaMock(...a),
}));

vi.mock('../services/productosService', () => ({
  fetchProductos: vi.fn().mockResolvedValue([]),
}));
vi.mock('../services/users', () => ({
  fetchUsuarios: vi.fn().mockResolvedValue([]),
}));
vi.mock('../services/sesionService', () => ({
  getSesionActiva: vi.fn().mockResolvedValue(null),
}));

import { useCotizacionForm } from '../hooks/useCotizacionForm';
import { usePedidoForm } from '../hooks/usePedidoForm';
import { useNotaVentaForm } from '../hooks/useNotaVentaForm';

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const DETALLE = {
  id_producto: 'p1',
  cantidad: '2',
  precio_unitario: '10',
  descuento_porcentaje: '',
  sku: 'SKU1',
  producto: 'Producto Uno',
  comentarios: '',
};

const PAGO: Pago = { id_metodo_pago: 'mp-1', id_moneda: 'mon-1', monto: 20, tasa: 1 };

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  getMock.mockResolvedValue([]);
  postMock.mockResolvedValue({});
  patchMock.mockResolvedValue({});
  cotizacionCreateMock.mockResolvedValue({ id_cotizacion: 'cot-1', numero_cotizacion: 'COT-1' });
  cotizacionUpdateMock.mockResolvedValue({ id_cotizacion: 'cot-1', numero_cotizacion: 'COT-1' });
  notaVentaCreateMock.mockResolvedValue({ id_nota_venta: 'nv-1', numero_nota_venta: 'NV-1' });
  notaVentaUpdateMock.mockResolvedValue({ id_nota_venta: 'nv-1', numero_nota_venta: 'NV-1' });
  createPagoDocumentoMock.mockResolvedValue({});
  crearClienteConEmpresaMock.mockResolvedValue({ id_cliente: 'cli-auto' });
});

// ── useCotizacionForm ─────────────────────────────────────────────────────────

describe('useCotizacionForm.submitCotizacion', () => {
  const values: CotizacionFormInput = {
    numero_cotizacion: '',
    fecha_cotizacion: '2026-06-11',
    fecha_vencimiento: '2026-07-11',
    estado: 'BORRADOR',
    id_empresa: 'emp-1',
    id_sucursal: 'suc-1',
    id_cliente: 'cli-1',
    id_moneda: 'mon-1',
    id_caja: '',
    id_vendedor: '',
    observaciones: '',
    condiciones_comerciales: '',
    detalles: [DETALLE],
  };

  it('crea la cotización con subtotales decimales, envía pagos y resetea', async () => {
    const { result } = renderHook(() => useCotizacionForm(), { wrapper: createWrapper() });

    let numero: string | null = null;
    await act(async () => {
      numero = await result.current.submitCotizacion(values, [PAGO]);
    });

    expect(numero).toBe('COT-1');
    expect(cotizacionCreateMock).toHaveBeenCalledTimes(1);
    const [payload] = cotizacionCreateMock.mock.calls[0] as [Record<string, unknown>];
    // El número lo asigna el backend: no se envía en creación.
    expect(payload).not.toHaveProperty('numero_cotizacion');
    const detalles = payload.detalles as Array<Record<string, unknown>>;
    expect(detalles[0].subtotal).toBe('20.00');
    expect(createPagoDocumentoMock).toHaveBeenCalledWith('COTIZACION', 'cot-1', PAGO);
    expect(result.current.numeroCotizacionCreado).toBe('COT-1');
    expect(result.current.success).toMatch(/creada exitosamente/i);
    // El formulario quedó reseteado para una nueva captura.
    expect(result.current.getValues('detalles')).toEqual([]);
  });

  it('avisa cuando la cotización se crea pero los pagos fallan', async () => {
    createPagoDocumentoMock.mockRejectedValue(new Error('pago falló'));
    const { result } = renderHook(() => useCotizacionForm(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.submitCotizacion(values, [PAGO]);
    });
    expect(result.current.success).toMatch(/error con los pagos/i);
  });

  it('sin cliente: si la autocreación falla devuelve null y no llama al servicio', async () => {
    const { result } = renderHook(() => useCotizacionForm(), { wrapper: createWrapper() });

    let numero: string | null = 'sentinel';
    await act(async () => {
      // clienteManual vacío → crearClienteAuto devuelve null.
      numero = await result.current.submitCotizacion({ ...values, id_cliente: '' });
    });
    expect(numero).toBeNull();
    expect(cotizacionCreateMock).not.toHaveBeenCalled();
  });

  it('sin cliente: autocrea el cliente y usa su id en el payload', async () => {
    const { result } = renderHook(() => useCotizacionForm(), { wrapper: createWrapper() });

    act(() => {
      result.current.setClienteManual({
        razon_social: 'Auto SA', rif: 'J-1', telefono: '0212-1', direccion: '', correo: '', codigo_cliente: '',
      });
    });
    await act(async () => {
      await result.current.submitCotizacion({ ...values, id_cliente: '' });
    });
    expect(crearClienteConEmpresaMock).toHaveBeenCalledWith(expect.objectContaining({ id_empresa: 'emp-1' }));
    const [payload] = cotizacionCreateMock.mock.calls[0] as [Record<string, unknown>];
    expect(payload.id_cliente).toBe('cli-auto');
  });

  it('en edición llama update y NO resetea el formulario', async () => {
    getMock.mockResolvedValue({});
    const { result } = renderHook(() => useCotizacionForm('cot-1'), { wrapper: createWrapper() });

    let numero: string | null = null;
    await act(async () => {
      numero = await result.current.submitCotizacion(values);
    });
    expect(numero).toBe('COT-1');
    expect(cotizacionUpdateMock).toHaveBeenCalledTimes(1);
    expect(cotizacionCreateMock).not.toHaveBeenCalled();
    expect(result.current.success).toMatch(/actualizada exitosamente/i);
  });

  it('marca error y devuelve null cuando el servicio falla', async () => {
    cotizacionCreateMock.mockRejectedValue(new Error('500'));
    const { result } = renderHook(() => useCotizacionForm(), { wrapper: createWrapper() });

    let numero: string | null = 'sentinel';
    await act(async () => {
      numero = await result.current.submitCotizacion(values);
    });
    expect(numero).toBeNull();
    expect(result.current.error).toBe('Error al crear la cotización');
    expect(result.current.loading).toBe(false);
  });
});

// ── usePedidoForm ─────────────────────────────────────────────────────────────

describe('usePedidoForm.submitPedido', () => {
  const values: PedidoFormInput = {
    numero_pedido: '',
    fecha_pedido: '2026-06-11',
    id_empresa: 'emp-1',
    id_sucursal: 'suc-1',
    id_cliente: 'cli-1',
    id_caja: '',
    id_vendedor: '',
    observaciones: '',
    detalles: [DETALLE],
  };

  it('crea el pedido vía POST con subtotales decimales y envía pagos', async () => {
    postMock.mockResolvedValue({ id_pedido: 'ped-1', numero_pedido: 'PED-1' });
    const { result } = renderHook(() => usePedidoForm(), { wrapper: createWrapper() });

    let numero: string | null = null;
    await act(async () => {
      numero = await result.current.submitPedido(values, [PAGO]);
    });
    expect(numero).toBe('PED-1');
    expect(postMock).toHaveBeenCalledWith('/ventas/pedidos/', expect.objectContaining({ id_cliente: 'cli-1' }));
    const [, payload] = postMock.mock.calls[0] as [string, Record<string, unknown>];
    expect(payload).not.toHaveProperty('numero_pedido');
    expect((payload.detalles as Array<Record<string, unknown>>)[0].subtotal).toBe('20.00');
    expect(createPagoDocumentoMock).toHaveBeenCalledWith('PEDIDO', 'ped-1', PAGO);
    expect(result.current.numeroPedidoCreado).toBe('PED-1');
  });

  it('en edición llama PATCH al endpoint del pedido', async () => {
    patchMock.mockResolvedValue({ id_pedido: 'ped-7', numero_pedido: 'PED-7' });
    const { result } = renderHook(() => usePedidoForm('ped-7'), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.submitPedido(values);
    });
    expect(patchMock).toHaveBeenCalledWith('/ventas/pedidos/ped-7/', expect.any(Object));
    expect(result.current.success).toMatch(/actualizado exitosamente/i);
  });

  it('marca error cuando el POST falla', async () => {
    postMock.mockRejectedValue(new Error('500'));
    const { result } = renderHook(() => usePedidoForm(), { wrapper: createWrapper() });

    let numero: string | null = 'sentinel';
    await act(async () => {
      numero = await result.current.submitPedido(values);
    });
    expect(numero).toBeNull();
    expect(result.current.error).toBe('Error al crear el pedido');
  });
});

// ── useNotaVentaForm ──────────────────────────────────────────────────────────

describe('useNotaVentaForm.submitNotaVenta', () => {
  const values: NotaVentaFormInput = {
    numero_nota_venta: '',
    fecha_emision: '2026-06-11',
    id_empresa: 'emp-1',
    id_sucursal: 'suc-1',
    id_cliente: 'cli-1',
    id_caja: '',
    id_vendedor: '',
    observaciones: '',
    detalles: [DETALLE],
  };

  it('crea la nota con detalles numéricos e id_cliente anidado', async () => {
    const { result } = renderHook(() => useNotaVentaForm(), { wrapper: createWrapper() });

    let numero: string | null = null;
    await act(async () => {
      numero = await result.current.submitNotaVenta(values, [PAGO]);
    });
    expect(numero).toBe('NV-1');
    const [payload] = notaVentaCreateMock.mock.calls[0] as [Record<string, unknown>];
    expect(payload.id_cliente).toEqual({ id_cliente: 'cli-1' });
    const detalles = payload.detalles as Array<Record<string, unknown>>;
    expect(detalles[0]).toMatchObject({ cantidad: 2, precio_unitario: 10, subtotal: 20 });
    expect(createPagoDocumentoMock).toHaveBeenCalledWith('NOTA_VENTA', 'nv-1', PAGO);
    expect(result.current.numeroNotaVentaCreado).toBe('NV-1');
  });

  it('carga una nota existente en el formulario al editar', async () => {
    getMock.mockImplementation((url: string) => {
      if (url.includes('/ventas/notas-venta/nv-9/')) {
        return Promise.resolve({
          id_nota_venta: 'nv-9',
          numero_nota_venta: 'NV-9',
          fecha_emision: '2026-05-01T10:00:00Z',
          id_empresa: 'emp-1',
          id_cliente: { id_cliente: 'cli-9' },
          observaciones: 'Nota previa',
          detalles: [{ id_producto: 'p9', cantidad: 3, precio_unitario: 7 }],
        });
      }
      return Promise.resolve([]);
    });
    const { result } = renderHook(() => useNotaVentaForm('nv-9'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.getValues('numero_nota_venta')).toBe('NV-9'));
    expect(result.current.getValues('fecha_emision')).toBe('2026-05-01');
    expect(result.current.getValues('id_cliente')).toBe('cli-9');
    expect(result.current.getValues('detalles')).toHaveLength(1);
    expect(result.current.getValues('detalles.0.cantidad')).toBe('3');
  });

  it('en edición llama update y marca éxito de actualización', async () => {
    const { result } = renderHook(() => useNotaVentaForm('nv-1'), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.submitNotaVenta(values);
    });
    expect(notaVentaUpdateMock).toHaveBeenCalledTimes(1);
    expect(result.current.success).toMatch(/actualizada exitosamente/i);
  });

  it('marca error cuando la creación falla', async () => {
    notaVentaCreateMock.mockRejectedValue(new Error('500'));
    const { result } = renderHook(() => useNotaVentaForm(), { wrapper: createWrapper() });

    let numero: string | null = 'sentinel';
    await act(async () => {
      numero = await result.current.submitNotaVenta(values);
    });
    expect(numero).toBeNull();
    expect(result.current.error).toBe('Error al crear la nota de venta');
  });
});
