// ─── Tipos compartidos del módulo ModalPago ───────────────────────────────────

export interface MetodoPago {
  id_metodo_pago: string;
  nombre_metodo: string;
  tipo_metodo: string;
}

export type MetodoPagoEmpresaActiva = {
  id?: number;
  empresa: string;
  metodo_pago: string;
  activa: boolean;
};

export interface Moneda {
  id_moneda: string;
  nombre: string;
  codigo_iso: string;
  es_base?: boolean;
  es_pais?: boolean;
}

export type MonedaEmpresaActiva = {
  id?: number;
  empresa: string;
  moneda: string;
  activa: boolean;
};

export interface Pago {
  id_metodo_pago: string;
  id_moneda: string;
  monto: number;
  referencia?: string;
  tasa: number;
  tipo_tasa?: string;
  monto_base?: number;
  monto_pais?: number;
  observaciones?: string;
  id_caja_fisica?: string;
  id_caja_virtual?: string;
  id_cuenta_bancaria?: string;
  id_datafono?: string;
  banco_destino?: string;
  // Campos de compatibilidad con el backend heredado
  metodo?: string;
  moneda?: string;
}

export type Paginated<T> = {
  results: T[];
  count?: number;
  next?: string | null;
  previous?: string | null;
};

export function isPaginated<T>(data: unknown): data is Paginated<T> {
  return (
    !!data &&
    typeof data === 'object' &&
    Array.isArray((data as { results?: unknown }).results)
  );
}

export interface ParametroSistema {
  id_parametro: string;
  codigo_parametro: string;
  valor_parametro: string;
  tipo_dato: string;
}

export interface CajaVirtual {
  id_caja: string;
  nombre: string;
  moneda: string;
  moneda_codigo_iso?: string;
  id_moneda: string;
  activa: boolean;
  caja_fisica?: string;
}

export interface NotaCredito {
  id_nota_credito: string;
  numero_nota: string;
  monto_disponible: number;
  id_moneda: string;
  fecha_emision: string;
  fecha_vencimiento?: string;
  descripcion?: string;
}

export interface CuentaBancaria {
  id_cuenta_bancaria: string;
  nombre_cuenta: string;
  numero_cuenta: string;
  id_moneda: string;
  id_banco: string;
  nombre_banco: string;
  metodos_pago?: string[];
  monedas?: string[];
}

export interface Datafono {
  id_datafono: string;
  nombre: string;
  id_moneda: string;
  id_cuenta_bancaria: string;
  metodos_pago?: string[];
  monedas?: string[];
}

export interface ModalPagoProps {
  open: boolean;
  monto: number;
  onClose: () => void;
  onConfirm: (
    pagos: Pago[],
    vueltos?: Pago[],
    notasCreditoUtilizadas?: NotaCredito[]
  ) => void;
  empresaId?: string;
  tipoDocumento?:
    | 'PEDIDO'
    | 'CXP'
    | 'GASTO'
    | 'NOTA_VENTA'
    | 'FACTURA'
    | 'NOMINA'
    | 'IMPUESTO'
    | 'COTIZACION';
  idDocumento?: string;
  idCliente?: string;
  idProveedor?: string;
  tipoOperacionInicial?: 'INGRESO' | 'EGRESO';
}
