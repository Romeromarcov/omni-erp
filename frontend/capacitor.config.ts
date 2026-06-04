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
