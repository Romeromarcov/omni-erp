export interface CarteraBucket {
  count: number;
  total: string;
}

export interface CarteraAging {
  buckets: {
    al_dia: CarteraBucket;
    '1_30': CarteraBucket;
    '31_60': CarteraBucket;
    '61_90': CarteraBucket;
    mas_90: CarteraBucket;
  };
  total_pendiente: string;
  total_partidas: number;
  partidas_vencidas: number;
  tasa_bcv_hoy: string | null;
  top_prioridades: PrioridadCliente[];
}

export interface PrioridadCliente {
  cliente_id: string;
  cliente_nombre: string;
  orden_ref: string;
  monto_pendiente: string;
  dias_vencida: number;
  bucket: string;
  score: string;
}

export interface GestionCobranza {
  id: string;
  empresa: string;
  cliente_id: string;
  cliente_nombre: string;
  orden_ref: string;
  canal: 'whatsapp' | 'email' | 'llamada' | 'visita' | 'carta';
  resultado: 'contactado' | 'sin_respuesta' | 'promesa_pago' | 'negativa' | 'acuerdo_logrado';
  notas: string;
  score: string;
  fecha_gestion: string;
  proxima_accion: string | null;
  created_at: string;
}

export interface CuotaAcuerdo {
  id: string;
  numero_cuota: number;
  fecha_vencimiento: string;
  monto: string;
  estado: 'pendiente' | 'pagado' | 'parcial' | 'vencido';
  monto_pagado: string;
  fecha_pago: string | null;
}

export interface AcuerdoPago {
  id: string;
  cliente_id: string;
  cliente_nombre: string;
  monto_total: string;
  periodicidad: 'unico' | 'semanal' | 'quincenal' | 'mensual';
  plazo_total_dias: number;
  fecha_inicio: string;
  monto_cuota: string | null;
  porcentaje_abono: string | null;
  estado: 'vigente' | 'cumplido' | 'roto' | 'cancelado';
  moneda_codigo: string;
  cuotas: CuotaAcuerdo[];
}

export interface PlantillaCobranza {
  id: string;
  nombre: string;
  canal: string;
  asunto: string;
  cuerpo: string;
  activa: boolean;
}

// For calcularCuotasPreview (TypeScript port of generar_cuotas)
export interface CuotaPreview {
  numero: number;
  fecha_vencimiento: string;
  monto: number;
}
