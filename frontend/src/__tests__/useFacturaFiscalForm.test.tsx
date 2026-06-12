/**
 * Q1/COV-2 escalón 3: tests de useFacturaFiscalForm (el único hook de documento
 * de venta sin suite propia). Cubre: creación con pagos (Decimal en subtotales),
 * error parcial de pagos, autocreación de cliente (éxito y fallo), carga de una
 * factura existente al editar, precarga desde la sesión de caja activa,
 * actualización y rama de error del servicio.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { Pago } from '../components/Pedidos/types';
import type { FacturaFiscalFormInput } from '../schemas/ventas.schemas';

// ── Mocks de red y servicios ──────────────────────────────────────────────────
const getMock = vi.fn();
vi.mock('../services/api', () => ({
  get: (...a: unknown[]) => getMock(...a),
  post: vi.fn().mockResolvedValue({}),
  patch: vi.fn().mockResolvedValue({}),
}));

const facturaCreateMock = vi.fn();
const facturaUpdateMock = vi.fn();
vi.mock('../services/ventas', () => ({
  FacturaFiscalService: class {
    create(...a: unknown[]) { return facturaCreateMock(...a); }
    update(...a: unknown[]) { return facturaUpdateMock(...a); }
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
const getSesionActivaMock = vi.fn();
vi.mock('../services/sesionService', () => ({
  getSesionActiva: (...a: unknown[]) => getSesionActivaMock(...a),
}));

import { useFacturaFiscalForm } from '../hooks/useFacturaFiscalForm';

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const DETALLE = {
  id_producto: 'p1',
  cantidad: '3',
  precio_unitario: '10.10',
  descuento_porcentaje: '',
  sku: 'SKU1',
  producto: 'Producto Uno',
  comentarios: '',
};

const PAGO: Pago = { id_metodo_pago: 'mp-1', id_moneda: 'mon-1', monto: 30.3, tasa: 1 };

const VALUES: FacturaFiscalFormInput = {
  numero_factura: '',
  fecha_emision: '2026-06-11',
  id_empresa: 'emp-1',
  id_sucursal: 'suc-1',
  id_cliente: 'cli-1',
  id_caja: '',
  id_vendedor: '',
  observaciones: '',
  detalles: [DETALLE],
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  getMock.mockResolvedValue([]);
  getSesionActivaMock.mockResolvedValue(null);
  facturaCreateMock.mockResolvedValue({ id_factura: 'ff-1', numero_factura: 'FF-1' });
  facturaUpdateMock.mockResolvedValue({ id_factura: 'ff-1', numero_factura: 'FF-1' });
  createPagoDocumentoMock.mockResolvedValue({});
  crearClienteConEmpresaMock.mockResolvedValue({ id_cliente: 'cli-auto' });
});

describe('useFacturaFiscalForm.submitFacturaFiscal', () => {
  it('crea la factura con subtotales decimales exactos, envía pagos y resetea', async () => {
    const { result } = renderHook(() => useFacturaFiscalForm(), { wrapper: createWrapper() });

    let numero: string | null = null;
    await act(async () => {
      numero = await result.current.submitFacturaFiscal(VALUES, [PAGO]);
    });

    expect(numero).toBe('FF-1');
    expect(facturaCreateMock).toHaveBeenCalledTimes(1);
    const [payload] = facturaCreateMock.mock.calls[0] as [Record<string, unknown>];
    // El número lo asigna el backend; el cliente va anidado.
    expect(payload).not.toHaveProperty('numero_factura');
    expect(payload.id_cliente).toEqual({ id_cliente: 'cli-1' });
    const detalles = payload.detalles as Array<Record<string, unknown>>;
    // 3 × 10.10 = 30.30 exacto (decimal.js, sin error binario).
    expect(detalles[0].subtotal).toBe('30.30');
    expect(createPagoDocumentoMock).toHaveBeenCalledWith('FACTURA_FISCAL', 'ff-1', PAGO);
    expect(result.current.numeroFacturaCreado).toBe('FF-1');
    expect(result.current.success).toMatch(/creada exitosamente.*FF-1/i);
    expect(result.current.getValues('detalles')).toEqual([]);
  });

  it('avisa cuando la factura se crea pero los pagos fallan', async () => {
    createPagoDocumentoMock.mockRejectedValue(new Error('pago falló'));
    const { result } = renderHook(() => useFacturaFiscalForm(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.submitFacturaFiscal(VALUES, [PAGO]);
    });
    expect(result.current.success).toMatch(/error con los pagos/i);
  });

  it('sin cliente: si la autocreación falla devuelve null y no llama al servicio', async () => {
    const { result } = renderHook(() => useFacturaFiscalForm(), { wrapper: createWrapper() });

    let numero: string | null = 'sentinel';
    await act(async () => {
      numero = await result.current.submitFacturaFiscal({ ...VALUES, id_cliente: '' });
    });
    expect(numero).toBeNull();
    expect(facturaCreateMock).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });

  it('sin cliente: autocrea el cliente y usa su id en el payload', async () => {
    const { result } = renderHook(() => useFacturaFiscalForm(), { wrapper: createWrapper() });

    act(() => {
      result.current.setClienteManual({
        razon_social: 'Auto SA', rif: 'J-1', telefono: '0212-1', direccion: '', correo: '', codigo_cliente: '',
      });
    });
    await act(async () => {
      await result.current.submitFacturaFiscal({ ...VALUES, id_cliente: '' });
    });
    expect(crearClienteConEmpresaMock).toHaveBeenCalledWith(expect.objectContaining({ id_empresa: 'emp-1' }));
    const [payload] = facturaCreateMock.mock.calls[0] as [Record<string, unknown>];
    expect(payload.id_cliente).toEqual({ id_cliente: 'cli-auto' });
  });

  it('en edición llama update y NO resetea el formulario', async () => {
    const { result } = renderHook(() => useFacturaFiscalForm('ff-1'), { wrapper: createWrapper() });

    let numero: string | null = null;
    await act(async () => {
      numero = await result.current.submitFacturaFiscal(VALUES);
    });
    expect(numero).toBe('FF-1');
    expect(facturaUpdateMock).toHaveBeenCalledTimes(1);
    expect(facturaCreateMock).not.toHaveBeenCalled();
    expect(result.current.success).toMatch(/actualizada exitosamente/i);
  });

  it('marca error y devuelve null cuando el servicio falla', async () => {
    facturaCreateMock.mockRejectedValue(new Error('500'));
    const { result } = renderHook(() => useFacturaFiscalForm(), { wrapper: createWrapper() });

    let numero: string | null = 'sentinel';
    await act(async () => {
      numero = await result.current.submitFacturaFiscal(VALUES);
    });
    expect(numero).toBeNull();
    expect(result.current.error).toBe('Error al crear la factura fiscal');
    expect(result.current.loading).toBe(false);
  });
});

describe('useFacturaFiscalForm — carga y precarga', () => {
  it('carga una factura existente normalizando fecha, cliente y detalles a string', async () => {
    getMock.mockImplementation((url: string) => {
      if (url.includes('/ventas/facturas-fiscales/ff-9/')) {
        return Promise.resolve({
          id_factura: 'ff-9',
          numero_factura: 'FF-9',
          fecha_emision: '2026-05-01T10:00:00Z',
          id_empresa: 'emp-1',
          id_cliente: { id_cliente: 'cli-9' },
          observaciones: 'Factura previa',
          detalles: [{ id_producto: 'p9', cantidad: 3, precio_unitario: 7, descuento_porcentaje: 5 }],
        });
      }
      return Promise.resolve([]);
    });
    const { result } = renderHook(() => useFacturaFiscalForm('ff-9'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.getValues('numero_factura')).toBe('FF-9'));
    expect(result.current.getValues('fecha_emision')).toBe('2026-05-01');
    expect(result.current.getValues('id_cliente')).toBe('cli-9');
    expect(result.current.getValues('detalles')).toHaveLength(1);
    expect(result.current.getValues('detalles.0.cantidad')).toBe('3');
    expect(result.current.getValues('detalles.0.precio_unitario')).toBe('7');
    expect(result.current.getValues('detalles.0.descuento_porcentaje')).toBe('5');
    expect(result.current.loading).toBe(false);
  });

  it('precarga caja, sucursal y empresa desde la sesión de caja activa', async () => {
    getSesionActivaMock.mockResolvedValue({
      caja_fisica_principal: {
        id_caja: 'caja-7',
        nombre: 'Caja 7',
        sucursal: {
          id_sucursal: 'suc-7',
          nombre: 'Sucursal 7',
          empresa: { id_empresa: 'emp-7', nombre: 'Empresa 7' },
        },
      },
      usuario: { username: 'cajero' },
    });
    const { result } = renderHook(() => useFacturaFiscalForm(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.getValues('id_caja')).toBe('caja-7'));
    expect(result.current.getValues('id_sucursal')).toBe('suc-7');
    expect(result.current.getValues('id_empresa')).toBe('emp-7');
  });
});
