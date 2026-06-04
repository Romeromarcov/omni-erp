/**
 * Inicialización del shell nativo (Capacitor / Electron).
 * Es un no-op en web. Se invoca una vez al arrancar la app (main.tsx).
 *
 * - Marca `<html>` con clases de plataforma para activar safe-areas y estilos.
 * - Configura la status bar y el botón atrás de Android (Capacitor).
 * Las dependencias de Capacitor se cargan de forma diferida para no afectar
 * el bundle web ni romper el build cuando no hay runtime nativo.
 */
import { getPlatform, isCapacitorNative, isElectron } from './index';

export async function initNativeShell(): Promise<void> {
  if (typeof document === 'undefined') return;

  const root = document.documentElement;
  const platform = getPlatform();
  root.dataset.platform = platform;
  if (platform !== 'web') root.classList.add('omni-native');
  if (isElectron()) root.classList.add('omni-electron');

  if (!isCapacitorNative()) return;

  try {
    const { StatusBar, Style } = await import('@capacitor/status-bar');
    await StatusBar.setStyle({ style: Style.Light });
    // En Android, no superponer el contenido bajo la barra de estado.
    if (platform === 'android') {
      await StatusBar.setOverlaysWebView({ overlay: false });
    }
  } catch {
    /* status bar no disponible — se ignora */
  }

  try {
    const { App } = await import('@capacitor/app');
    App.addListener('backButton', ({ canGoBack }) => {
      if (canGoBack) window.history.back();
      else App.exitApp();
    });
  } catch {
    /* App plugin no disponible — se ignora */
  }
}
