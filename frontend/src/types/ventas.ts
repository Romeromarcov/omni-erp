// --- AGREGADO PARA TIPOS DE PEDIDO Y NOTA DE VENTA ---
export interface DetallePedido {
  id_detalle_pedido?: string;
  id_pedido?: string;
  id_producto: string;
  id_variante?: string;
  cantidad: number;
  precio_unitario: number;
  descuento_porcentaje: number;
  descuento_monto?: number;
  subtotal: number;
  monto_impuesto?: number;
  total_linea?: number;
  observaciones?: string;
  sku?: string;
  producto?: string;
}

export interface Pedido {
  id_pedido: string;
  numero_pedido: string;
  fecha_pedido: string;
  estado: string;
  id_empresa: string;
  id_sucursal: string;
  id_cliente: {
    id_cliente: string;
    nombre: string;
    razon_social?: string;
    rif?: string;
    telefono?: string;
    email?: string;
    direccion?: string;
    direccion_fiscal?: string;
  };
  id_moneda: string;
  id_caja?: string;
  id_vendedor?: string;
  observaciones?: string;
  condiciones_comerciales?: string;
  detalles: DetallePedido[];
  monto_total?: number;
  monto_impuesto?: number;
  monto_descuento?: number;
  subtotal?: number;
  // Props para integración
  convertido_a_nota_venta?: boolean;
  id_cotizacion_origen?: string;
}

export interface DetalleNotaVenta {
  id_detalle_nota_venta?: string;
  id_nota_venta?: string;
  id_producto: string;
  id_variante?: string;
  cantidad: number;
  precio_unitario: number;
  descuento_porcentaje: number;
  descuento_monto?: number;
  subtotal: number;
  monto_impuesto?: number;
  total_linea?: number;
  observaciones?: string;
  sku?: string;
  producto?: string;
}

export interface NotaVenta {
  id_nota_venta: string;
  numero_nota_venta: string;
  fecha_nota_venta: string;
  estado: string;
  id_empresa: string;
  id_sucursal: string;
  id_cliente: {
    id_cliente: string;
    nombre: string;
    razon_social?: string;
    rif?: string;
    telefono?: string;
    email?: string;
    direccion?: string;
    direccion_fiscal?: string;
  };
  id_moneda: string;
  id_caja?: string;
  id_vendedor?: string;
  observaciones?: string;
  condiciones_comerciales?: string;
  detalles: DetalleNotaVenta[];
  monto_total?: number;
  monto_impuesto?: number;
  monto_descuento?: number;
  subtotal?: number;
  // Props para integración
  convertido_a_factura?: boolean;
  id_pedido_origen?: string;
  numero_nota?: string;
  fecha_nota?: string;
}
export interface DetalleCotizacion {
  id_detalle_cotizacion?: string;
  id_cotizacion?: string;
  id_producto: string;
  id_variante?: string;
  cantidad: number;
  precio_unitario: number;
  descuento_porcentaje: number;
  descuento_monto?: number;
  subtotal: number;
  monto_impuesto?: number;
  total_linea?: number;
  observaciones?: string;
  sku?: string;
  producto?: string;
}

export interface Cotizacion {
  id_cotizacion: string;
  numero_cotizacion: string;
  fecha_cotizacion: string;
  fecha_vencimiento: string;
  estado: string;
  id_empresa: string;
  id_sucursal: string;
  id_cliente: {
    id_cliente: string;
    nombre: string;
    razon_social?: string;
    rif?: string;
    telefono?: string;
    email?: string;
    direccion?: string;
    direccion_fiscal?: string;
  };
  id_moneda: string;
  id_caja?: string;
  id_vendedor?: string;
  observaciones?: string;
  condiciones_comerciales?: string;
  detalles: DetalleCotizacion[];
  monto_total?: number;
  monto_impuesto?: number;
  monto_descuento?: number;
  subtotal?: number;
  // Props para integración
  convertido_a_pedido?: boolean;
}

export interface DetalleFacturaFiscal {
  id_detalle_factura: string;
  id_factura: string;
  id_producto: string;
  id_variante?: string;
  cantidad: number;
  precio_unitario: number;
  descuento_porcentaje: number;
  descuento_monto: number;
  subtotal: number;
  monto_impuesto: number;
  total_linea: number;
  observaciones?: string;
}

export interface FacturaFiscal {
  id_factura: string;
  id_empresa: string;
  id_cliente: {
    id_cliente: string;
    nombre: string;
    razon_social: string;
    rif: string;
    telefono: string;
  } | null;
  numero_factura: string;
  numero_control: string;
  fecha_emision: string;
  fecha_vencimiento?: string;
  id_moneda: string;
  tasa_cambio: number;
  estado: 'BORRADOR' | 'EMITIDA' | 'ANULADA' | 'PAGADA';
  base_imponible: number;
  monto_iva: number;
  monto_total: number;
  observaciones?: string;
  fecha_creacion: string;
  detalles: DetalleFacturaFiscal[];
  // Props para integración
  id_nota_venta_origen?: string;
  id_caja?: string;
}

export interface NotaCreditoVenta {
  id_nota_credito: string;
  id_empresa: string;
  id_cliente: {
    id_cliente: string;
    nombre: string;
    razon_social: string;
    rif: string;
    telefono: string;
  } | null;
  id_factura_origen?: string;
  numero_nota_credito: string;
  fecha_emision: string;
  motivo: 'DEVOLUCION' | 'DESCUENTO' | 'ERROR_FACTURACION' | 'ANULACION' | 'OTRO';
  monto_total: number;
  id_moneda: string;
  estado: 'BORRADOR' | 'EMITIDA' | 'APLICADA' | 'ANULADA';
  observaciones?: string;
  fecha_creacion: string;
  detalles?: DetalleNotaCreditoVenta[];
}

export interface DetalleNotaCreditoVenta {
  id_detalle_nota_credito: string;
  id_nota_credito: string;
  id_producto: string;
  id_variante?: string;
  cantidad: number;
  precio_unitario: number;
  subtotal: number;
  monto_impuesto: number;
  total_linea: number;
  observaciones?: string;
}

export interface NotaCreditoFiscal {
  id_nota_credito_fiscal: string;
  id_empresa: string;
  id_cliente: {
    id_cliente: string;
    nombre: string;
    razon_social: string;
    rif: string;
    telefono: string;
  } | null;

  // Enlaces fiscales
  id_factura_origen: string;
  numero_control: string;
  numero_nota_credito: string;

  fecha_emision: string;
  fecha_vencimiento?: string;

  // Montos
  base_imponible: number;
  monto_iva: number;
  monto_total: number;

  // Moneda e impuestos
  id_moneda: string;
  tasa_cambio: number;

  // Motivo fiscal
  motivo: 'DEVOLUCION' | 'DESCUENTO' | 'ERROR_FACTURACION' | 'ANULACION' | 'AJUSTE_PRECIO' | 'OTRO';

  // Estado fiscal
  estado: 'BORRADOR' | 'EMITIDA' | 'APLICADA' | 'ANULADA';

  // Control de inventario fiscal separado
  afecta_inventario_fiscal: boolean;

  referencia_externa?: string;
  documento_json?: Record<string, unknown>;
  observaciones?: string;
  activo: boolean;
  fecha_creacion: string;
  detalles?: DetalleNotaCreditoFiscal[];
}

export interface DetalleNotaCreditoFiscal {
  id_detalle_nota_credito: string;
  id_nota_credito_fiscal: string;
  id_producto: string;
  id_variante?: string;
  cantidad: number;
  precio_unitario: number;
  descuento_porcentaje: number;
  descuento_monto: number;
  subtotal: number;
  monto_impuesto: number;
  total_linea: number;
  observaciones?: string;
}

export interface DevolucionVenta {
  id_devolucion: string;
  id_empresa: string;
  id_cliente: {
    id_cliente: string;
    nombre: string;
    razon_social: string;
    rif: string;
    telefono: string;
  } | null;
  id_factura_origen?: string;
  // Nota de crédito generada automáticamente
  id_nota_credito_generada?: string;

  numero_devolucion: string;
  fecha_devolucion: string;
  motivo_devolucion: 'DEFECTO' | 'GARANTIA' | 'ERROR_ENTREGA' | 'CAMBIO_CLIENTE' | 'VENCIMIENTO' | 'OTRO';
  estado: 'PENDIENTE' | 'APROBADA' | 'PROCESADA' | 'RECHAZADA' | 'ANULADA';
  monto_total: number;
  id_moneda: string;
  observaciones?: string;
  fecha_creacion: string;
  detalles?: DetalleDevolucionVenta[];
}

export interface DetalleDevolucionVenta {
  id_detalle_devolucion: string;
  id_devolucion: string;
  id_producto: string;
  id_variante?: string;
  cantidad_devuelta: number;
  precio_unitario: number;
  subtotal: number;
  estado_producto: 'BUENO' | 'DEFECTUOSO' | 'VENCIDO' | 'DAÑADO';
  accion_inventario: 'REINTEGRAR' | 'CUARENTENA' | 'DESCARTAR' | 'REPARAR';
  observaciones?: string;
}