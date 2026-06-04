// Build de la app web para empaquetado nativo (Capacitor/Electron).
// Fuerza base relativa y hash routing; el resto del build es idéntico al web.
// VITE_API_URL debe venir del entorno (apunta al backend real).
import { execSync } from 'node:child_process';

process.env.VITE_BASE = './';
process.env.VITE_USE_HASH_ROUTER = 'true';

if (!process.env.VITE_API_URL) {
  console.warn(
    '[build-native] VITE_API_URL no definida; el build de producción fallará. ' +
      'Ej: VITE_API_URL=https://api.tu-dominio/api npm run build:native',
  );
}

execSync('npm run build', { stdio: 'inherit', env: process.env });
