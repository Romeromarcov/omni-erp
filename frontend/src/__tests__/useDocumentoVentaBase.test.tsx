/**
 * Q1/COV-2 escalón 2: tests de useDocumentoVentaBase (el hook base de todos los
 * formularios de documentos de venta). Cubre los handlers de staging de líneas,
 * los helpers de cliente (selección, RIF compuesto, similares, autocreación),
 * los callbacks de predeterminados (caja / sesión / vendedor) y la
 * normalización `toArray` de las queries de referencia.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { cotizacionFormSchema, type CotizacionFormInput } from '../schemas/ventas.schemas';
import type { Cliente } from '../services/clientesService';
import type { SesionCaja } from '../services/sesionService';
import type { Pago } from '../components/Pedidos/ModalPago';

// ── Mocks de servicios ────────────────────────────────────────────────────────
const getMock = vi.fn();
vi.mock('../services/api', () => ({
  get: (...a: unknown[]) => getMock(...a),
  post: vi.fn(),
  patch: vi.fn(),
}));

const fetchProductosMock = vi.fn();
vi.mock('../services/productosService', () => ({
  fetchProductos: (...a: unknown[]) => fetchProductosMock(...a),
}));

const buscarClientesMock = vi.fn();
const buscarClientesSimilaresMock = vi.fn();
const crearClienteConEmpresaMock = vi.fn();
vi.mock('../services/clientesService', () => ({
  buscarClientes: (...a: unknown[]) => buscarClientesMock(...a),
  buscarClientesSimilares: (...a: unknown[]) => buscarClientesSimilaresMock(...a),
  crearClienteConEmpresa: (...a: unknown[]) => crearClienteConEmpresaMock(...a),
}));

const fetchUsuariosMock = vi.fn();
vi.mock('../services/users', () => ({
  fetchUsuarios: (...a: unknown[]) => fetchUsuariosMock(...a),
}));

const getSesionActivaMock = vi.fn();
vi.mock('../services/sesionService', () => ({
  getSesionActiva: (...a: unknown[]) => getSesionActivaMock(...a),
}));

import { useDocumentoVentaBase } from '../hooks/useDocumentoVentaBase';

const SESION: SesionCaja = {
  id_sesion: 'ses-1',
  usuario: { id: 7, username: 'vendedor7', first_name: 'V', last_name: 'Siete' },
  caja_fisica_principal: {
    id_caja: 'caja-ses',
    nombre: 'Caja Sesión',
    sucursal: {
      id_sucursal: 'suc-ses',
      nombre: 'Sucursal Sesión',
      empresa: { id_empresa: 'emp-ses', nombre: 'Empresa Sesión' },
    },
  },
  estado: 'ABIERTA',
  fecha_apertura: '2026-06-01T08:00:00Z',
};

const defaultValues: CotizacionFormInput = {
  numero_cotizacion: '',
  fecha_cotizacion: '2026-06-11',
  fecha_vencimiento: '2026-07-11',
  estado: 'BORRADOR',
  id_empresa: 'emp-1',
  id_sucursal: 'suc-1',
  id_cliente: '',
  id_moneda: 'mon-1',
  id_caja: '',
  id_vendedor: '',
  observaciones: '',
  condiciones_comerciales: '',
  detalles: [],
};

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

type HookOptions = Partial<Parameters<typeof useDocumentoVentaBase<CotizacionFormInput>>[0]>;

function renderBase(options: HookOptions = {}) {
  return renderHook(
    () =>
      useDocumentoVentaBase<CotizacionFormInput>({
        schema: cotizacionFormSchema,
        defaultValues,
        ...options,
      }),
    { wrapper: createWrapper() },
  );
}

const changeEvent = (name: string, value: string) =>
  ({ target: { name, value } }) as unknown as React.ChangeEvent<HTMLInputElement>;

const keyEvent = (key: string, name: string) =>
  ({ key, currentTarget: { name } }) as unknown as React.KeyboardEvent<HTMLInputElement>;

const formEvent = () => ({ preventDefault: vi.fn() }) as unknown as React.FormEvent;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  getMock.mockResolvedValue([]);
  fetchProductosMock.mockResolvedValue([]);
  fetchUsuariosMock.mockResolvedValue([]);
  getSesionActivaMock.mockResolvedValue(null);
  buscarClientesMock.mockResolvedValue([]);
  buscarClientesSimilaresMock.mockResolvedValue([]);
  crearClienteConEmpresaMock.mockResolvedValue({ id_cliente: 'cli-auto' });
});

describe('useDocumentoVentaBase — datos de referencia y callbacks', () => {
  it('normaliza respuestas paginadas ({results}) y dispara onCajaPredet con la caja predeterminada', async () => {
    getMock.mockImplementation((url: string) => {
      if (url.includes('cajas-usuario')) {
        return Promise.resolve({
          results: [
            { es_predeterminada: false, caja: { id_caja: 'caja-x' } },
            { es_predeterminada: true, caja: { id_caja: 'caja-pred' } },
          ],
        });
      }
      return Promise.resolve([]);
    });
    const onCajaPredet = vi.fn();
    const { result } = renderBase({ onCajaPredet });

    await waitFor(() => expect(result.current.cajasUsuario).toHaveLength(2));
    expect(onCajaPredet).toHaveBeenCalledWith('caja-pred');
  });

  it('dispara onSesionCargada y prefiere al usuario de la sesión como vendedor', async () => {
    getSesionActivaMock.mockResolvedValue(SESION);
    fetchUsuariosMock.mockResolvedValue([
      { id: 3, username: 'otro' },
      { id: 7, username: 'vendedor7' },
    ]);
    const onSesionCargada = vi.fn();
    const onVendedorPredet = vi.fn();
    const { result } = renderBase({ onSesionCargada, onVendedorPredet });

    await waitFor(() => expect(result.current.sesionActiva).not.toBeNull());
    expect(onSesionCargada).toHaveBeenCalledWith(SESION);
    await waitFor(() => expect(onVendedorPredet).toHaveBeenCalledWith('7'));
  });

  it('usa el primer vendedor cuando el usuario de la sesión no está en la lista', async () => {
    getSesionActivaMock.mockResolvedValue(SESION);
    fetchUsuariosMock.mockResolvedValue([{ id: 99, username: 'unico' }]);
    const onVendedorPredet = vi.fn();
    renderBase({ onVendedorPredet });

    await waitFor(() => expect(onVendedorPredet).toHaveBeenCalledWith('99'));
  });

  it('solo consulta empresas cuando NO hay sesión activa', async () => {
    getSesionActivaMock.mockResolvedValue(null);
    getMock.mockImplementation((url: string) => {
      if (url.includes('/core/empresas/')) {
        return Promise.resolve([{ id_empresa: 'emp-1', nombre_legal: 'ACME' }]);
      }
      return Promise.resolve([]);
    });
    const { result } = renderBase();

    await waitFor(() => expect(result.current.empresas).toHaveLength(1));
    expect(result.current.empresas[0].nombre_legal).toBe('ACME');
  });

  it('devuelve listas vacías ante respuestas con forma inesperada', async () => {
    getMock.mockResolvedValue({ inesperado: true });
    fetchProductosMock.mockResolvedValue({ inesperado: true });
    const { result } = renderBase();

    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(result.current.cajasUsuario).toEqual([]);
    expect(result.current.productos).toEqual([]);
    expect(result.current.sucursales).toEqual([]);
  });
});

describe('useDocumentoVentaBase — staging de líneas de producto', () => {
  it('handleDetalleChange actualiza el campo y handleAddDetalle agrega al field-array', async () => {
    const { result } = renderBase();

    act(() => {
      result.current.handleDetalleChange(changeEvent('id_producto', 'p1'));
      result.current.handleDetalleChange(changeEvent('cantidad', '2'));
      result.current.handleDetalleChange(changeEvent('precio_unitario', '10.50'));
    });
    expect(result.current.detalleForm.id_producto).toBe('p1');

    act(() => {
      result.current.handleAddDetalle(formEvent());
    });
    expect(result.current.detallesArray.fields).toHaveLength(1);
    // El staging se limpia tras agregar.
    expect(result.current.detalleForm.id_producto).toBe('');
    expect(result.current.detalleForm.cantidad).toBe('');
  });

  it('handleAddDetalle NO agrega si falta producto, cantidad o precio', () => {
    const { result } = renderBase();

    act(() => {
      result.current.handleDetalleChange(changeEvent('cantidad', '2'));
      result.current.handleAddDetalle(formEvent());
    });
    expect(result.current.detallesArray.fields).toHaveLength(0);
  });

  it('handleRemoveDetalle quita la línea agregada', () => {
    const { result } = renderBase();

    act(() => {
      result.current.handleDetalleChange(changeEvent('id_producto', 'p1'));
      result.current.handleDetalleChange(changeEvent('cantidad', '1'));
      result.current.handleDetalleChange(changeEvent('precio_unitario', '5'));
    });
    act(() => {
      result.current.handleAddDetalle(formEvent());
    });
    expect(result.current.detallesArray.fields).toHaveLength(1);

    act(() => {
      result.current.handleRemoveDetalle(0);
    });
    expect(result.current.detallesArray.fields).toHaveLength(0);
  });

  it('selectProducto copia id, precio sugerido, sku y nombre al staging', () => {
    const { result } = renderBase();

    act(() => {
      result.current.selectProducto({
        id_producto: 'p9',
        nombre_producto: 'Monitor',
        sku: 'MON-9',
        precio_venta_sugerido: 120,
      });
    });
    expect(result.current.detalleForm).toMatchObject({
      id_producto: 'p9',
      precio_unitario: '120',
      sku: 'MON-9',
      producto: 'Monitor',
    });
  });

  it('selectProducto deja el precio vacío si el producto no tiene precio sugerido', () => {
    const { result } = renderBase();

    act(() => {
      result.current.selectProducto({ id_producto: 'p2', nombre_producto: 'Sin precio' });
    });
    expect(result.current.detalleForm.precio_unitario).toBe('');
  });
});

describe('useDocumentoVentaBase — manejo de cliente', () => {
  const CLIENTE: Cliente = {
    id_cliente: 'cli-1',
    razon_social: 'Cliente Uno CA',
    rif: 'J-12345678',
    telefono: '0414-0000000',
  };

  it('selectCliente fija el id, llena clienteManual (con fallbacks) y marca éxito', () => {
    const { result } = renderBase();
    const clienteConExtras = {
      ...CLIENTE,
      direccion_fiscal: 'Av. Principal',
      email: 'uno@cliente.com',
      codigo_cliente: 'C-001',
    };
    const setClienteId = vi.fn();

    act(() => {
      result.current.selectCliente(clienteConExtras, setClienteId);
    });
    expect(setClienteId).toHaveBeenCalledWith('cli-1');
    expect(result.current.clienteManual).toMatchObject({
      razon_social: 'Cliente Uno CA',
      rif: 'J-12345678',
      direccion: 'Av. Principal',
      correo: 'uno@cliente.com',
      codigo_cliente: 'C-001',
    });
    expect(result.current.success).toMatch(/seleccionado correctamente/i);
  });

  it('handleClienteManualChange compone el RIF desde prefijo y número', () => {
    const { result } = renderBase();

    act(() => {
      result.current.handleClienteManualChange(changeEvent('rif_prefijo', 'J'));
    });
    expect(result.current.clienteManual.rif).toBe('J');

    act(() => {
      result.current.handleClienteManualChange(changeEvent('rif_numero', '87654321'));
    });
    expect(result.current.clienteManual.rif).toBe('J-87654321');

    act(() => {
      result.current.handleClienteManualChange(changeEvent('razon_social', 'Nueva CA'));
    });
    expect(result.current.clienteManual.razon_social).toBe('Nueva CA');

    // Un nombre desconocido no toca el estado.
    act(() => {
      result.current.handleClienteManualChange(changeEvent('campo_fantasma', 'x'));
    });
    expect(result.current.clienteManual.razon_social).toBe('Nueva CA');
  });

  it('handleClienteBlur avisa cuando hay clientes similares', async () => {
    buscarClientesSimilaresMock.mockResolvedValue([CLIENTE]);
    const { result } = renderBase();

    act(() => {
      result.current.setClienteManual({
        razon_social: 'Cliente Uno', rif: 'J-12345678', telefono: '', direccion: '', correo: '', codigo_cliente: '',
      });
    });
    await act(async () => {
      await result.current.handleClienteBlur();
    });
    expect(buscarClientesSimilaresMock).toHaveBeenCalledWith('Cliente Uno', 'J-12345678', 'emp-1');
    expect(result.current.clientesSimilares).toHaveLength(1);
    expect(result.current.success).toMatch(/clientes similares/i);
  });

  it('handleClienteBlur limpia el aviso si no hay similares y no consulta sin datos', async () => {
    const { result } = renderBase();

    // Sin razón social ni rif: no consulta.
    await act(async () => {
      await result.current.handleClienteBlur();
    });
    expect(buscarClientesSimilaresMock).not.toHaveBeenCalled();

    act(() => {
      result.current.setClienteManual({
        razon_social: 'Cliente Dos', rif: 'J-22222222', telefono: '', direccion: '', correo: '', codigo_cliente: '',
      });
    });
    await act(async () => {
      await result.current.handleClienteBlur();
    });
    expect(result.current.clientesSimilares).toHaveLength(0);
    expect(result.current.success).toBe('');
  });

  it('handleClienteBlur ignora errores del servicio de similares', async () => {
    buscarClientesSimilaresMock.mockRejectedValue(new Error('red caída'));
    const { result } = renderBase();

    act(() => {
      result.current.setClienteManual({
        razon_social: 'Cliente Tres', rif: 'J-3', telefono: '', direccion: '', correo: '', codigo_cliente: '',
      });
    });
    await act(async () => {
      await result.current.handleClienteBlur();
    });
    expect(result.current.error).toBe('');
  });

  it('handleClienteManualKeyDown selecciona el cliente que coincide exacto por razón social', async () => {
    buscarClientesMock.mockResolvedValue([CLIENTE]);
    const { result } = renderBase();
    const setClienteId = vi.fn();

    act(() => {
      result.current.setClienteManual({
        razon_social: '  cliente uno ca ', rif: '', telefono: '', direccion: '', correo: '', codigo_cliente: '',
      });
    });
    await act(async () => {
      await result.current.handleClienteManualKeyDown(keyEvent('Enter', 'razon_social'), setClienteId);
    });
    expect(buscarClientesMock).toHaveBeenCalled();
    expect(setClienteId).toHaveBeenCalledWith('cli-1');
  });

  it('handleClienteManualKeyDown por RIF no selecciona si no hay match exacto', async () => {
    buscarClientesMock.mockResolvedValue([CLIENTE]);
    const { result } = renderBase();
    const setClienteId = vi.fn();

    act(() => {
      result.current.setClienteManual({
        razon_social: '', rif: 'J-99999999', telefono: '', direccion: '', correo: '', codigo_cliente: '',
      });
    });
    await act(async () => {
      await result.current.handleClienteManualKeyDown(keyEvent('Enter', 'rif'), setClienteId);
    });
    expect(setClienteId).not.toHaveBeenCalled();
  });

  it('handleClienteManualKeyDown ignora teclas distintas de Enter y consultas vacías', async () => {
    const { result } = renderBase();
    const setClienteId = vi.fn();

    await act(async () => {
      await result.current.handleClienteManualKeyDown(keyEvent('Tab', 'razon_social'), setClienteId);
      await result.current.handleClienteManualKeyDown(keyEvent('Enter', 'razon_social'), setClienteId);
    });
    expect(buscarClientesMock).not.toHaveBeenCalled();
    expect(setClienteId).not.toHaveBeenCalled();
  });

  it('crearClienteAuto crea el cliente con los datos manuales y devuelve su id', async () => {
    const { result } = renderBase();

    act(() => {
      result.current.setClienteManual({
        razon_social: 'Nuevo SA', rif: 'J-11111111', telefono: '0212-5555555',
        direccion: 'Calle 1', correo: 'n@n.com', codigo_cliente: '',
      });
    });
    let id: string | null = null;
    await act(async () => {
      id = await result.current.crearClienteAuto('emp-1');
    });
    expect(id).toBe('cli-auto');
    expect(crearClienteConEmpresaMock).toHaveBeenCalledWith(expect.objectContaining({
      razon_social: 'Nuevo SA', rif: 'J-11111111', id_empresa: 'emp-1',
    }));
    expect(result.current.success).toMatch(/creado y seleccionado/i);
  });

  it('crearClienteAuto devuelve null sin llamar al servicio si faltan datos obligatorios', async () => {
    const { result } = renderBase();

    let id: string | null = 'sentinel';
    await act(async () => {
      id = await result.current.crearClienteAuto('emp-1');
    });
    expect(id).toBeNull();
    expect(crearClienteConEmpresaMock).not.toHaveBeenCalled();
  });

  it('crearClienteAuto marca error cuando el servicio falla', async () => {
    crearClienteConEmpresaMock.mockRejectedValue(new Error('500'));
    const { result } = renderBase();

    act(() => {
      result.current.setClienteManual({
        razon_social: 'Falla SA', rif: 'J-2', telefono: '0212-1', direccion: '', correo: '', codigo_cliente: '',
      });
    });
    let id: string | null = 'sentinel';
    await act(async () => {
      id = await result.current.crearClienteAuto('emp-1');
    });
    expect(id).toBeNull();
    expect(result.current.error).toBe('Error al crear el cliente');
  });
});

describe('useDocumentoVentaBase — helpers de formulario', () => {
  it('setClienteId escribe id_cliente en el formulario RHF', () => {
    const { result } = renderBase();

    act(() => {
      result.current.setClienteId('cli-55');
    });
    expect(result.current.getValues('id_cliente')).toBe('cli-55');
  });

  it('resetAuxState limpia staging, pagos, descuento y cliente manual', () => {
    const { result } = renderBase();

    act(() => {
      result.current.setDetalleForm({ id_producto: 'p1', cantidad: '1', precio_unitario: '2' });
      const pago: Pago = { id_metodo_pago: 'mp-1', id_moneda: 'mon-1', monto: 10, tasa: 1 };
      result.current.setPagos([pago]);
      result.current.setDescuentoGeneral('5');
      result.current.setClienteManual({
        razon_social: 'X', rif: 'J-1', telefono: '1', direccion: '', correo: '', codigo_cliente: '',
      });
    });
    act(() => {
      result.current.resetAuxState();
    });
    expect(result.current.detalleForm.id_producto).toBe('');
    expect(result.current.pagos).toEqual([]);
    expect(result.current.descuentoGeneral).toBe('');
    expect(result.current.clienteManual.razon_social).toBe('');
  });

  it('getFieldString devuelve string para valores presentes y vacío para nulos/no-objetos', () => {
    const { result } = renderBase();
    const { getFieldString } = result.current;

    expect(getFieldString({ a: 1 }, 'a')).toBe('1');
    expect(getFieldString({ a: null }, 'a')).toBe('');
    expect(getFieldString(null, 'a')).toBe('');
    expect(getFieldString('texto', 'a')).toBe('');
  });
});
