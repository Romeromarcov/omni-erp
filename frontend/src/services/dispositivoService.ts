import { post } from './api';
import type { DispositivoAccionRequest, DispositivoAccionResponse } from '../types/dispositivos';

/**
 * Servicio para manejar acciones relacionadas con dispositivos
 */
export class DispositivoService {
  /**
   * Ejecuta una acción sobre un dispositivo
   */
  static async ejecutarAccion(accionData: DispositivoAccionRequest): Promise<DispositivoAccionResponse> {
    return post<DispositivoAccionResponse>('/core/dispositivos/accion/', accionData as unknown as Record<string, unknown>);
  }

  /**
   * Crea una caja física para un dispositivo
   */
  static async crearCajaFisica(
    idDispositivo: string,
    nombreCaja: string,
    tipoCaja: string = 'REGISTRADORA'
  ): Promise<DispositivoAccionResponse> {
    return this.ejecutarAccion({
      id_dispositivo: idDispositivo,
      accion: 'crear_caja_fisica',
      nombre_caja: nombreCaja,
      tipo_caja: tipoCaja
    });
  }

  /**
   * Marca que no se debe preguntar más por caja física para este dispositivo
   */
  static async noPreguntarCaja(idDispositivo: string): Promise<DispositivoAccionResponse> {
    return this.ejecutarAccion({
      id_dispositivo: idDispositivo,
      accion: 'no_preguntar_caja'
    });
  }

  /**
   * Abre una sesión en la caja física asociada al dispositivo
   */
  static async abrirSesion(idDispositivo: string): Promise<DispositivoAccionResponse> {
    return this.ejecutarAccion({
      id_dispositivo: idDispositivo,
      accion: 'abrir_sesion'
    });
  }
}