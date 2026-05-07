import { get, post, put, del } from './api';

export interface CajaVirtual {
  id_caja: string;
  nombre: string;
  tipo_caja: string;
  tipo_caja_display: string;
  descripcion?: string;
  moneda_codigo_iso: string;
  activa: boolean;
  empresa_nombre?: string;
  sucursal_nombre?: string;
  saldo_actual: number;
  fecha_creacion: string;
}

export interface Datafono {
  id_datafono: string;
  nombre: string;
  serial: string;
  activo: boolean;
  saldo_actual: number;
  ultima_conexion?: string;
  empresa_nombre?: string;
  sucursal_nombre?: string;
  cuenta_bancaria_nombre?: string;
  fecha_creacion: string;
}

export interface CajaFisica {
  id_caja_fisica: string;
  nombre: string;
  tipo_caja: string;
  tipo_caja_display: string;
  sucursal?: string;
  sucursal_nombre?: string;
  moneda?: string;
  identificador_dispositivo?: string;
  nombre_dispositivo?: string;
  tipo_dispositivo?: string;
  descripcion_dispositivo?: string;
  requiere_sesion_activa: boolean;
  activa: boolean;
  descripcion?: string;
  empresa_nombre?: string;
  fecha_creacion?: string;
  cajas_virtuales?: CajaVirtual[];
  datafonos?: Datafono[];
  esta_abierta: boolean;
  estado_sesion_display: string;
  nombre_usuario_actual?: string;
}

export interface MovimientoCajaBanco {
  id_movimiento: string;
  tipo_movimiento: string;
  monto: number;
  fecha_movimiento: string;
  hora_movimiento: string;
  concepto: string;
  referencia?: string;
  id_moneda: string;
  id_caja_fisica?: string;
  id_cuenta_bancaria?: string;
  saldo_anterior: number;
  saldo_nuevo: number;
  id_usuario_registro: string;
}

export interface CierreCajaRequest {
  saldo_real: number;
  hasta?: string;
}

export interface CierreCajaResponse {
  ingresos: number;
  egresos: number;
  saldo_teorico: number;
  saldo_real: number;
  descuadre: number;
  movimiento_cierre_id: string;
  movimiento_ajuste_id?: string;
  fecha_cierre: string;
  mensaje: string;
}

class CajasFisicasService {
  private baseUrl = '/finanzas/cajas-fisicas';

  // Obtener todas las cajas físicas
  async getCajasFisicas(params?: {
    page?: number;
    page_size?: number;
    search?: string;
    ordering?: string;
    empresa?: string;
    sucursal?: string;
    activa?: boolean;
  }): Promise<{ results: CajaFisica[]; count: number }> {
    const queryParams = params ? new URLSearchParams(params as Record<string, string>).toString() : '';
    const url = queryParams ? `${this.baseUrl}?${queryParams}` : this.baseUrl;
    return get<{ results: CajaFisica[]; count: number }>(url);
  }

  // Obtener una caja física por ID
  async getCajaFisica(id: string): Promise<CajaFisica> {
    return get<CajaFisica>(`${this.baseUrl}/${id}`);
  }

  // Crear una nueva caja física
  async createCajaFisica(data: Omit<CajaFisica, 'id_caja_fisica' | 'fecha_creacion' | 'empresa_nombre' | 'sucursal_nombre' | 'moneda_codigo_iso' | 'tipo_caja_display'>): Promise<CajaFisica> {
    return post<CajaFisica>(this.baseUrl, data as Record<string, unknown>);
  }

  // Actualizar una caja física
  async updateCajaFisica(id: string, data: Partial<CajaFisica>): Promise<CajaFisica> {
    return put<CajaFisica>(`${this.baseUrl}/${id}`, data as Record<string, unknown>);
  }

  // Eliminar una caja física
  async deleteCajaFisica(id: string): Promise<void> {
    return del(`${this.baseUrl}/${id}`);
  }

  // Realizar cierre de caja
  async cerrarCaja(id: string, data: CierreCajaRequest): Promise<CierreCajaResponse> {
    return post<CierreCajaResponse>(`${this.baseUrl}/${id}/cierre`, data as unknown as Record<string, unknown>);
  }

  // Obtener opciones de tipo de caja
  async getTipoCajaChoices(): Promise<Array<{ value: string; display: string }>> {
    return get<Array<{ value: string; display: string }>>(`${this.baseUrl}/tipo-caja-choices`);
  }

  // Obtener cajas virtuales asociadas a una caja física
  async getCajasVirtualesAsociadas(id: string): Promise<CajaVirtual[]> {
    return get<CajaVirtual[]>(`${this.baseUrl}/${id}/cajas-virtuales`);
  }

  // Obtener datafonos asociados a una caja física
  async getDatafonosAsociados(id: string): Promise<Datafono[]> {
    return get<Datafono[]>(`${this.baseUrl}/${id}/datafonos`);
  }

  // Abrir sesión de caja
  async abrirSesion(id: string): Promise<{
    mensaje: string;
    sesion: {
      id_sesion: string;
      estado: string;
      fecha_apertura: string;
      usuario: string;
    };
  }> {
    return post<{
      mensaje: string;
      sesion: {
        id_sesion: string;
        estado: string;
        fecha_apertura: string;
        usuario: string;
      };
    }>(`${this.baseUrl}/${id}/abrir-sesion/`, {});
  }

  // Cerrar sesión de caja
  async cerrarSesion(id: string, notasCierre?: string): Promise<{
    mensaje: string;
    sesion: {
      id_sesion: string;
      estado: string;
      fecha_cierre: string;
      duracion_minutos: number;
    };
  }> {
    return post<{
      mensaje: string;
      sesion: {
        id_sesion: string;
        estado: string;
        fecha_cierre: string;
        duracion_minutos: number;
      };
    }>(`${this.baseUrl}/${id}/cerrar-sesion/`, { notas_cierre: notasCierre });
  }
}

export const cajasFisicasService = new CajasFisicasService();