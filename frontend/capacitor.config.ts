import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Configuración de Capacitor para las apps nativas móviles (iOS/Android).
 * La app web compilada (`dist/`) se empaqueta dentro del contenedor nativo.
 *
 * Build nativo:  VITE_BASE=./ VITE_API_URL=https://api.tu-dominio/api npm run build
 * Sincronizar:   npm run cap:sync
 */
const config: CapacitorConfig = {
  appId: 'com.omnierp.app',
  appName: 'Omni ERP',
  webDir: 'dist',
  backgroundColor: '#f4f6f8',
  ios: {
    contentInset: 'always',
  },
  android: {
    allowMixedContent: false,
  },
  server: {
    // Explícito (default de Capacitor ≥5): el WebView sirve la app bajo
    // https://localhost — origen estable que el CORS del backend permite
    // (settings_prod.py, orígenes de shells nativos) y contexto seguro para
    // la cookie httpOnly de refresh (Secure).
    androidScheme: 'https',
  },
  plugins: {
    StatusBar: {
      style: 'LIGHT',
      backgroundColor: '#1976d2',
    },
    Keyboard: {
      resize: 'native',
    },
  },
};

export default config;
