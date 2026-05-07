/**
 * Utilidades para detección de dispositivos
 */

/**
 * Genera un fingerprint único y consistente para el dispositivo actual.
 * El fingerprint se basa en características del navegador y hardware que
 * deberían ser consistentes para el mismo dispositivo.
 */
export function generateDeviceFingerprint(): string {
  try {
    // Crear un canvas para obtener características únicas del hardware de renderizado
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      throw new Error('Canvas not supported');
    }

    // Configurar el contexto de dibujo
    ctx.textBaseline = 'top';
    ctx.font = '14px Arial';
    ctx.fillText('Fingerprint', 2, 2);

    // Obtener datos de canvas (únicos por hardware/driver)
    const canvasData = canvas.toDataURL();

    // Recopilar características del navegador y dispositivo
    const screenInfo = `${screen.width}x${screen.height}x${screen.colorDepth}`;
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const language = navigator.language;
    const platform = navigator.platform;
    const cookieEnabled = navigator.cookieEnabled;
    const doNotTrack = navigator.doNotTrack;

    // Crear un string único con todas las características
    const fingerprintString = [
      canvasData,
      screenInfo,
      timezone,
      language,
      platform,
      cookieEnabled,
      doNotTrack,
      'hardwareConcurrency' in navigator ? (navigator as { hardwareConcurrency?: number }).hardwareConcurrency : 'unknown',
      'deviceMemory' in navigator ? (navigator as { deviceMemory?: number }).deviceMemory : 'unknown'
    ].join('|');

    // Generar hash usando Web Crypto API si está disponible
    if (window.crypto && window.crypto.subtle) {
      // Para un hash consistente, usamos una función simple de hash
      // En producción, podrías usar una librería como crypto-js
      return simpleHash(fingerprintString).toString(36).slice(0, 32);
    } else {
      // Fallback para navegadores sin crypto API
      return simpleHash(fingerprintString).toString(36).slice(0, 32);
    }
  } catch (error) {
    console.warn('Error generating device fingerprint:', error);
    // Fallback: generar un ID aleatorio pero consistente por sesión
    const fallbackId = localStorage.getItem('device_fallback_id');
    if (fallbackId) {
      return fallbackId;
    } else {
      const newId = `fallback_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      localStorage.setItem('device_fallback_id', newId);
      return newId;
    }
  }
}

/**
 * Función de hash simple para generar un número a partir de un string
 */
function simpleHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convertir a 32 bits
  }
  return Math.abs(hash);
}

/**
 * Obtiene o genera el fingerprint del dispositivo actual
 */
export function getDeviceFingerprint(): string {
  const stored = localStorage.getItem('device_fingerprint');
  if (stored) {
    return stored;
  }

  const fingerprint = generateDeviceFingerprint();
  localStorage.setItem('device_fingerprint', fingerprint);
  return fingerprint;
}

/**
 * Obtiene información adicional del dispositivo para el login
 */
export function getDeviceInfo() {
  return {
    device_fingerprint: getDeviceFingerprint(),
    device_user_agent: navigator.userAgent,
    device_ip: undefined // El backend obtendrá la IP del request
  };
}