// Tipos para el sistema de detección de dispositivos
import type { Usuario } from '../services/users';

export interface Dispositivo {
  id_dispositivo: string;
  fingerprint: string;
  nombre_dispositivo: string;
  user_agent: string;
  ip_address: string;
  empresa: {
    id_empresa: string;
    nombre: string;
  };
  sucursal: {
    id_sucursal: string;
    nombre: string;
  };
  caja_fisica?: {
    id_caja_fisica: string;
    nombre: string;
    tipo_caja: string;
  };
  tiene_caja_fisica: boolean;
  preguntar_crear_caja: boolean;
  puede_crear_caja_fisica: boolean;
  fecha_registro: string;
  ultimo_login?: string;
  creado: boolean;
  activo: boolean;
}

export interface DispositivoInfo {
  id_dispositivo: string;
  nombre_dispositivo: string;
  creado: boolean;
  accion: 'nada' | 'preguntar_caja' | 'abrir_sesion' | 'abrir_sesion_automatico' | 'sesion_activa';
  mensaje: string;
  datos?: {
    caja_fisica?: {
      id_caja_fisica: string;
      nombre: string;
    };
    sesion?: {
      id_sesion: string;
      estado: string;
      fecha_apertura: string;
    };
    dispositivo?: Dispositivo;
    empresa?: {
      id_empresa: string;
      nombre: string;
    };
    sucursal?: {
      id_sucursal: string;
      nombre: string;
    };
    user_agent?: string;
    ip_address?: string;
  };
  sesion_abierta?: {
    id_sesion: string;
    estado: string;
    fecha_apertura: string;
    caja_fisica: {
      id_caja_fisica: string;
      nombre: string;
    };
  };
  error_sesion?: string;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  user: Usuario;
  dispositivo?: DispositivoInfo;
}

export interface DispositivoAccionRequest {
  id_dispositivo: string;
  accion: 'crear_caja_fisica' | 'no_preguntar_caja' | 'abrir_sesion';
  nombre_caja?: string;
  tipo_caja?: string;
}

export interface DispositivoAccionResponse {
  success: boolean;
  mensaje: string;
  caja_fisica?: {
    id_caja_fisica: string;
    nombre: string;
    tipo_caja: string;
  };
  sesion?: {
    id_sesion: string;
    estado: string;
    fecha_apertura: string;
    caja_fisica: {
      id_caja_fisica: string;
      nombre: string;
    };
  };
  error?: string;
}