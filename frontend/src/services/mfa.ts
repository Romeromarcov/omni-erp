import { get, post } from './api';
import type { LoginResponse } from '../types/dispositivos';

export interface MfaEstado {
  habilitado: boolean;
  confirmado_en: string | null;
  codigos_respaldo_restantes: number;
  requerido_por_politica: boolean;
}

export interface MfaIniciarResponse {
  otpauth_uri: string;
  qr_svg: string;
  secret_manual: string;
}

export interface MfaConfirmarResponse {
  habilitado: boolean;
  confirmado_en: string;
  codigos_respaldo: string[];
}

export interface MfaCodigosResponse {
  codigos_respaldo: string[];
}

export interface MfaDesactivarResponse {
  habilitado: boolean;
}

export async function getMfaEstado(): Promise<MfaEstado> {
  return get<MfaEstado>('/auth/mfa/estado/');
}

export async function iniciarMfa(): Promise<MfaIniciarResponse> {
  return post<MfaIniciarResponse>('/auth/mfa/iniciar/', {});
}

export async function confirmarMfa(codigo: string): Promise<MfaConfirmarResponse> {
  return post<MfaConfirmarResponse>('/auth/mfa/confirmar/', { codigo });
}

export async function desactivarMfa(password: string, codigo: string): Promise<MfaDesactivarResponse> {
  return post<MfaDesactivarResponse>('/auth/mfa/desactivar/', { password, codigo });
}

export async function regenerarCodigosMfa(codigo: string): Promise<MfaCodigosResponse> {
  return post<MfaCodigosResponse>('/auth/mfa/regenerar-codigos/', { codigo });
}

export async function verificarMfaLogin(
  mfaToken: string,
  codigo: string,
  deviceInfo: Record<string, unknown> = {},
): Promise<LoginResponse> {
  return post<LoginResponse>('/auth/mfa/verificar/', {
    mfa_token: mfaToken,
    codigo,
    ...deviceInfo,
  });
}
