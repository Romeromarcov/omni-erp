/**
 * Detección de plataforma de ejecución para la base multiplataforma de Omni ERP.
 *
 * Una sola base React/Vite corre en: navegador/PWA (web), iOS/Android (Capacitor)
 * y Windows (Electron). Estas utilidades permiten adaptar router, safe-areas y
 * acceso a hardware (escáner) según dónde se ejecute la app.
 */

export type PlatformName = 'web' | 'ios' | 'android' | 'electron';

interface ElectronBridge {
  isElectron: boolean;
  platform: string;
}

interface CapacitorGlobal {
  isNativePlatform?: () => boolean;
  getPlatform?: () => string;
}

declare global {
  interface Window {
    Capacitor?: CapacitorGlobal;
    omniDesktop?: ElectronBridge;
  }
}

/** True si corre dentro del contenedor de escritorio (Electron/Windows). */
export function isElectron(): boolean {
  return typeof window !== 'undefined' && !!window.omniDesktop?.isElectron;
}

/** True si corre como app nativa móvil empaquetada con Capacitor (iOS/Android). */
export function isCapacitorNative(): boolean {
  const cap = typeof window !== 'undefined' ? window.Capacitor : undefined;
  return !!(cap && typeof cap.isNativePlatform === 'function' && cap.isNativePlatform());
}

/** True en cualquier shell nativo (Electron o Capacitor). */
export function isNative(): boolean {
  return isElectron() || isCapacitorNative();
}

/** Nombre normalizado de la plataforma activa. */
export function getPlatform(): PlatformName {
  if (isElectron()) return 'electron';
  const cap = typeof window !== 'undefined' ? window.Capacitor : undefined;
  const p = cap?.getPlatform?.();
  if (p === 'ios' || p === 'android') return p;
  return 'web';
}

/**
 * Los shells nativos cargan la app desde `file://` (Electron) o un origen
 * embebido (Capacitor) donde la History API basada en rutas no resuelve
 * recargas/deep-links; ahí usamos hash routing. La web usa rutas limpias.
 */
export function shouldUseHashRouter(): boolean {
  if (typeof window !== 'undefined' && window.location.protocol === 'file:') return true;
  const env = import.meta.env as Record<string, string | undefined>;
  if (env.VITE_USE_HASH_ROUTER === 'true') return true;
  return isNative();
}
