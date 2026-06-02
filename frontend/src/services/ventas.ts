import { get, post, patch, fetcher } from './api';
import { toList } from '../utils/api';
import type {
  Cotizacion,
  Pedido,
  NotaVenta,
  FacturaFiscal,
  NotaCreditoVenta,
  NotaCreditoFiscal,
  DevolucionVenta
} from '../types/ventas';

// Función delete
async function delete_<T>(endpoint: string): Promise<void> {
  await fetcher<T>(endpoint, { method: 'DELETE' });
}

// Tipos para conversiones
interface ConversionData {
  [key: string]: unknown;
}

interface PagoData {
  metodo: string;
  moneda: string;
  monto: number;
  tasa: number;
  referencia?: string;
  observacion?: string;
}

// Tipos para respuestas paginadas
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// Servicio base para operaciones CRUD comunes
class BaseVentasService<T> {
  protected endpoint: string;

  constructor(endpoint: string) {
    this.endpoint = endpoint;
  }

  async getAll(): Promise<T[]> {
    const response = await get<PaginatedResponse<T> | T[]>(`/${this.endpoint}/`);
    return toList<T>(response);
  }

  async getAllPaginated(page = 1, pageSize = 20): Promise<PaginatedResponse<T>> {
    const response = await get<PaginatedResponse<T> | T[]>(
      `/${this.endpoint}/?page=${page}&page_size=${pageSize}`
    );
    if (response && typeof response === 'object' && 'results' in response) {
      return response as PaginatedResponse<T>;
    }
    const arr = Array.isArray(response) ? response : [];
    return { count: arr.length, next: null, previous: null, results: arr };
  }

  async getById(id: string): Promise<T> {
    return get<T>(`/${this.endpoint}/${id}/`);
  }

  async create(data: Partial<Omit<T, 'id' | 'fecha_creacion'>>): Promise<T> {
    return post<T>(`/${this.endpoint}/`, data as Record<string, unknown>);
  }

  async update(id: string, data: Partial<T>): Promise<T> {
    return patch<T>(`/${this.endpoint}/${id}/`, data as Record<string, unknown>);
  }

  async delete(id: string): Promise<void> {
    await delete_<void>(`/${this.endpoint}/${id}/`);
  }
}

// Servicios específicos para cada tipo de documento
export class CotizacionService extends BaseVentasService<Cotizacion> {
  constructor() {
    super('ventas/cotizaciones');
  }

  async convertirAPedido(id: string, data: ConversionData): Promise<Pedido> {
    return post<Pedido>(`/ventas/cotizaciones/${id}/convertir-pedido/`, data);
  }

  async getByCliente(clienteId: string): Promise<Cotizacion[]> {
    return get<Cotizacion[]>(`/ventas/cotizaciones/?id_cliente=${clienteId}`);
  }
}

export class PedidoService extends BaseVentasService<Pedido> {
  constructor() {
    super('ventas/pedidos');
  }

  async convertirANotaVenta(id: string, data: ConversionData): Promise<NotaVenta> {
    return post<NotaVenta>(`/ventas/pedidos/${id}/convertir-nota-venta/`, data);
  }

  async getByCliente(clienteId: string): Promise<Pedido[]> {
    return get<Pedido[]>(`/ventas/pedidos/?id_cliente=${clienteId}`);
  }

  async agregarPago(id: string, pagoData: PagoData): Promise<Pedido> {
    return post<Pedido>(`/ventas/pedidos/${id}/agregar-pago/`, pagoData as unknown as Record<string, unknown>);
  }
}

export class NotaVentaService extends BaseVentasService<NotaVenta> {
  constructor() {
    super('ventas/notas-venta');
  }

  async convertirAFactura(id: string, data: ConversionData): Promise<FacturaFiscal> {
    return post<FacturaFiscal>(`/ventas/notas-venta/${id}/convertir-factura/`, data);
  }

  async getByCliente(clienteId: string): Promise<NotaVenta[]> {
    return get<NotaVenta[]>(`/ventas/notas-venta/?id_cliente=${clienteId}`);
  }
}

export class FacturaFiscalService extends BaseVentasService<FacturaFiscal> {
  constructor() {
    super('ventas/facturas-fiscales');
  }

  async getByCliente(clienteId: string): Promise<FacturaFiscal[]> {
    return get<FacturaFiscal[]>(`/ventas/facturas-fiscales/?id_cliente=${clienteId}`);
  }

  async generarNotaCredito(id: string, motivo: string, data: ConversionData): Promise<NotaCreditoFiscal> {
    return post<NotaCreditoFiscal>(`/ventas/facturas-fiscales/${id}/generar-nota-credito/`, {
      motivo,
      ...data
    });
  }
}

export class NotaCreditoVentaService extends BaseVentasService<NotaCreditoVenta> {
  constructor() {
    super('ventas/notas-credito-venta');
  }

  async aplicar(id: string): Promise<NotaCreditoVenta> {
    return post<NotaCreditoVenta>(`/ventas/notas-credito-venta/${id}/aplicar/`, {});
  }
}

export class NotaCreditoFiscalService extends BaseVentasService<NotaCreditoFiscal> {
  constructor() {
    super('ventas/notas-credito-fiscal');
  }

  async aplicar(id: string): Promise<NotaCreditoFiscal> {
    return post<NotaCreditoFiscal>(`/ventas/notas-credito-fiscal/${id}/aplicar/`, {});
  }
}

export class DevolucionVentaService extends BaseVentasService<DevolucionVenta> {
  constructor() {
    super('ventas/devoluciones-venta');
  }

  async procesar(id: string): Promise<DevolucionVenta> {
    return post<DevolucionVenta>(`/ventas/devoluciones-venta/${id}/procesar/`, {});
  }

  async generarNotaCredito(id: string): Promise<NotaCreditoFiscal> {
    return post<NotaCreditoFiscal>(`/ventas/devoluciones-venta/${id}/generar-nota-credito/`, {});
  }
}

// Instancias de servicios
export const cotizacionService = new CotizacionService();
export const pedidoService = new PedidoService();
export const notaVentaService = new NotaVentaService();
export const facturaFiscalService = new FacturaFiscalService();
export const notaCreditoVentaService = new NotaCreditoVentaService();
export const notaCreditoFiscalService = new NotaCreditoFiscalService();
export const devolucionVentaService = new DevolucionVentaService();