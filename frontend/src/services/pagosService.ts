import { get, post, put, del } from './api';
import type { NotaCredito, Pago as PagoModal } from '../components/Pedidos/ModalPago';

export interface Pago {
  id_pago?: string;
  id_empresa: string;
  tipo_operacion: 'INGRESO' | 'EGRESO';
  tipo_documento: string;
  id_documento: string;
  fecha_pago: string;
  monto: number;
  id_moneda: string;
  tasa: number;
  id_metodo_pago: string;
  referencia?: string;
  observaciones?: string;
  id_caja_fisica?: string;
  id_caja_virtual?: string;
  id_cuenta_bancaria?: string;
  id_datafono?: string;
  banco_destino?: string;
  // Campos adicionales para compatibilidad con backend
  metodo?: string;
  moneda?: string;
  // Relaciones opcionales específicas
  id_pedido?: string;
  id_nota_venta?: string;
  id_factura?: string;
  id_cxp?: string;
  id_gasto?: string;
  id_reembolso_gasto?: string;
  id_nomina?: string;
  id_contribucion?: string;
  // Objetos relacionados (opcionales, para UI)
  id_metodo_pago_obj?: { id_metodo_pago: string; nombre_metodo: string };
  id_moneda_obj?: { id_moneda: string; codigo_iso: string; nombre: string };
}

export interface PagoFilters {
  tipo_documento?: string;
  tipo_operacion?: 'INGRESO' | 'EGRESO';
  fecha_desde?: string;
  fecha_hasta?: string;
  id_empresa?: string;
  id_documento?: string;
}

export const pagosService = {
  // ==========================================
  // MÉTODOS GENÉRICOS PARA TODOS LOS DOCUMENTOS
  // ==========================================

  /**
   * Crear pago para cualquier tipo de documento
   * @param tipoDocumento - Tipo de documento (PEDIDO, CXP, GASTO, etc.)
   * @param idDocumento - ID del documento específico
   * @param pagoData - Datos del pago
   * @returns Promise<Pago> - El pago creado
   *
   * @example
   * // Crear pago para un pedido
   * const pago = await pagosService.createPagoDocumento('PEDIDO', '123', {
   *   monto: 100,
   *   id_metodo_pago: 'mp-456',
   *   id_moneda: 'mon-789',
   *   tasa: 1
   * });
   *
   * // Crear pago para una cuenta por pagar
   * const pagoCXP = await pagosService.createPagoDocumento('CXP', 'cxp-123', {
   *   monto: 500,
   *   id_metodo_pago: 'mp-transfer',
   *   id_moneda: 'mon-ves',
   *   tasa: 35.5
   * });
   */
  async getPagos(filters?: PagoFilters): Promise<Pago[]> {
    const params = new URLSearchParams();

    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          params.append(key, value.toString());
        }
      });
    }

    const queryString = params.toString();
    const url = `/finanzas/pagos/${queryString ? `?${queryString}` : ''}`;

    const response = await get<{ results: Pago[] } | Pago[]>(url);
    return Array.isArray(response) ? response : response.results || [];
  },

  // Obtener un pago específico
  async getPago(id: string): Promise<Pago> {
    return await get<Pago>(`/finanzas/pagos/${id}/`);
  },

  // Crear un nuevo pago
  async createPago(pago: Omit<Pago, 'id_pago'>): Promise<Pago> {
    return await post<Pago>('/finanzas/pagos/', pago);
  },

  /**
   * Procesar vueltos creando movimientos de caja/banco
   * @param vueltos - Array de pagos que representan vueltos
   * @returns Promise<void>
   */
  async procesarVueltos(_vueltos: PagoModal[]): Promise<void> {
    // Stub: el backend maneja el procesamiento de vueltos automáticamente
  },

  /**
   * Conciliar notas de crédito
   * @param notasCredito - Array de notas de crédito a conciliar
   * @param idDocumento - ID del documento que las utiliza
   * @param tipoDocumento - Tipo del documento
   * @returns Promise<void>
   */
  async conciliarNotasCredito(notasCredito: NotaCredito[], idDocumento: string, tipoDocumento: string): Promise<void> {
    for (const nota of notasCredito) {
      // Marcar la nota como utilizada/conciliada
      await put(`/finanzas/notas-credito/${nota.id_nota_credito}/`, {
        estado: 'UTILIZADA',
        id_documento_utilizado: idDocumento,
        tipo_documento_utilizado: tipoDocumento,
        fecha_utilizacion: new Date().toISOString()
      });
    }
  },

  // Actualizar un pago existente
  async updatePago(id: string, pago: Partial<Pago>): Promise<Pago> {
    return await put<Pago>(`/finanzas/pagos/${id}/`, pago);
  },

  // Eliminar un pago
  async deletePago(id: string): Promise<void> {
    return await del(`/finanzas/pagos/${id}/`);
  },

  // Obtener pagos por tipo de documento
  async getPagosByTipoDocumento(tipoDocumento: string, idDocumento?: string): Promise<Pago[]> {
    const filters: PagoFilters = { tipo_documento: tipoDocumento };
    if (idDocumento) {
      filters.id_documento = idDocumento;
    }
    return await this.getPagos(filters);
  },

  // Obtener pagos de un pedido específico
  async getPagosPedido(idPedido: string): Promise<Pago[]> {
    return await this.getPagosByTipoDocumento('PEDIDO', idPedido);
  },

  // Obtener pagos de una cuenta por pagar específica
  async getPagosCXP(idCXP: string): Promise<Pago[]> {
    return await this.getPagosByTipoDocumento('CXP', idCXP);
  },

  // Obtener pagos de un gasto específico
  async getPagosGasto(idGasto: string): Promise<Pago[]> {
    return await this.getPagosByTipoDocumento('GASTO', idGasto);
  },

  // Obtener pagos de una nota de venta específica
  async getPagosNotaVenta(idNotaVenta: string): Promise<Pago[]> {
    return await this.getPagosByTipoDocumento('NOTA_VENTA', idNotaVenta);
  },

  // Crear pago para cualquier tipo de documento
  async createPagoDocumento(
    tipoDocumento: string,
    idDocumento: string,
    pagoData: {
      monto: number;
      id_metodo_pago: string;
      id_moneda: string;
      tasa: number;
      referencia?: string;
      observaciones?: string;
      id_caja_fisica?: string;
      id_caja_virtual?: string;
      id_cuenta_bancaria?: string;
      id_datafono?: string;
      banco_destino?: string;
    }
  ): Promise<Pago> {
    // Determinar el tipo de operación basado en el tipo de documento
    const tipoOperacion = this.getTipoOperacionPorDocumento(tipoDocumento);

    // Obtener información del documento para completar los datos
    const documentoInfo = await this.getDocumentoInfo(tipoDocumento, idDocumento);

    // Obtener nombres de método de pago y moneda
    const [metodoInfo, monedaInfo] = await Promise.all([
      this.getMetodoPagoInfo(pagoData.id_metodo_pago),
      this.getMonedaInfo(pagoData.id_moneda)
    ]);

    const pago: Omit<Pago, 'id_pago'> = {
      id_empresa: documentoInfo.id_empresa,
      tipo_operacion: tipoOperacion,
      tipo_documento: tipoDocumento,
      id_documento: idDocumento,
      fecha_pago: new Date().toISOString(),
      monto: pagoData.monto,
      id_moneda: pagoData.id_moneda,
      tasa: pagoData.tasa,
      id_metodo_pago: pagoData.id_metodo_pago,
      referencia: pagoData.referencia,
      observaciones: pagoData.observaciones,
      id_caja_fisica: pagoData.id_caja_fisica,
      id_caja_virtual: pagoData.id_caja_virtual,
      id_cuenta_bancaria: pagoData.id_cuenta_bancaria,
      id_datafono: pagoData.id_datafono,
      banco_destino: pagoData.banco_destino,
      // Campos adicionales requeridos por el backend
      metodo: metodoInfo.nombre_metodo,
      moneda: monedaInfo.codigo_iso,
      // Asignar el campo específico del documento
      ...this.getDocumentoField(tipoDocumento, idDocumento),
    };

    return await this.createPago(pago);
  },

  // Determinar tipo de operación basado en el tipo de documento
  getTipoOperacionPorDocumento(tipoDocumento: string): 'INGRESO' | 'EGRESO' {
    const documentosIngreso = ['PEDIDO', 'NOTA_VENTA', 'FACTURA', 'FACTURA_FISCAL', 'COTIZACION'];
    const documentosEgreso = ['CXP', 'GASTO', 'REEMBOLSO_GASTO', 'NOMINA', 'IMPUESTO', 'AJUSTE', 'TRANSFERENCIA'];

    if (documentosIngreso.includes(tipoDocumento)) {
      return 'INGRESO';
    } else if (documentosEgreso.includes(tipoDocumento)) {
      return 'EGRESO';
    } else {
      // Por defecto EGRESO para documentos desconocidos
      return 'EGRESO';
    }
  },

  // Obtener información del documento (empresa)
  async getDocumentoInfo(tipoDocumento: string, idDocumento: string): Promise<{ id_empresa: string }> {
    let endpoint = '';

    switch (tipoDocumento) {
      case 'PEDIDO':
        endpoint = `/ventas/pedidos/${idDocumento}/`;
        break;
      case 'NOTA_VENTA':
        endpoint = `/ventas/notas-venta/${idDocumento}/`;
        break;
      case 'FACTURA':
        endpoint = `/ventas/facturas/${idDocumento}/`;
        break;
      case 'FACTURA_FISCAL':
        endpoint = `/ventas/facturas-fiscales/${idDocumento}/`;
        break;
      case 'COTIZACION':
        endpoint = `/ventas/cotizaciones/${idDocumento}/`;
        break;
      case 'CXP':
        endpoint = `/cuentas-por-pagar/cxp/${idDocumento}/`;
        break;
      case 'GASTO':
        endpoint = `/gastos/gastos/${idDocumento}/`;
        break;
      case 'REEMBOLSO_GASTO':
        endpoint = `/gastos/reembolsos/${idDocumento}/`;
        break;
      case 'NOMINA':
        endpoint = `/nomina/nominas/${idDocumento}/`;
        break;
      case 'IMPUESTO':
        endpoint = `/fiscal/contribuciones/${idDocumento}/`;
        break;
      default:
        throw new Error(`Tipo de documento no soportado: ${tipoDocumento}`);
    }

    const response = await get(endpoint) as { id_empresa: string };
    return { id_empresa: response.id_empresa };
  },

  // Obtener el campo específico del documento
  getDocumentoField(tipoDocumento: string, idDocumento: string): Partial<Pago> {
    switch (tipoDocumento) {
      case 'PEDIDO':
        return { id_pedido: idDocumento };
      case 'NOTA_VENTA':
        return { id_nota_venta: idDocumento };
      case 'FACTURA':
        return { id_factura: idDocumento };
      case 'FACTURA_FISCAL':
        return { id_factura: idDocumento };
      case 'COTIZACION':
        return {};
      case 'CXP':
        return { id_cxp: idDocumento };
      case 'GASTO':
        return { id_gasto: idDocumento };
      case 'REEMBOLSO_GASTO':
        return { id_reembolso_gasto: idDocumento };
      case 'NOMINA':
        return { id_nomina: idDocumento };
      case 'IMPUESTO':
        return { id_contribucion: idDocumento };
      default:
        return {};
    }
  },

  // Funciones auxiliares para obtener información de método de pago y moneda
  async getMetodoPagoInfo(idMetodoPago: string): Promise<{ nombre_metodo: string }> {
    try {
      const metodo = await get(`/finanzas/metodos-pago/${idMetodoPago}/`) as { nombre_metodo?: string; nombre?: string };
      return { nombre_metodo: metodo.nombre_metodo || metodo.nombre || idMetodoPago };
    } catch (error) {
      void error;
      return { nombre_metodo: idMetodoPago }; // Fallback al ID
    }
  },

  async getMonedaInfo(idMoneda: string): Promise<{ codigo_iso: string }> {
    try {
      const moneda = await get(`/finanzas/monedas/${idMoneda}/`) as { codigo_iso?: string };
      return { codigo_iso: moneda.codigo_iso || idMoneda };
    } catch (error) {
      void error;
      return { codigo_iso: idMoneda }; // Fallback al ID
    }
  },
};