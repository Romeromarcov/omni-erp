import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// BACKEND_URL puede venir del entorno:
//   - Local dev:  no se setea → default localhost:8000
//   - Docker dev: se setea como http://backend:8000 en docker-compose.yml
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const backendUrl: string = (globalThis as any).process?.env?.BACKEND_URL ?? 'http://localhost:8000'

// Base de assets: '/' para web/PWA; './' (relativa) para builds nativos
// (Electron carga con file:// y Capacitor desde un origen embebido).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const base: string = (globalThis as any).process?.env?.VITE_BASE ?? '/'

// https://vite.dev/config/
export default defineConfig({
  base,
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'robots.txt'],
      manifest: {
        name: 'OmniERP',
        short_name: 'OmniERP',
        description: 'Sistema ERP empresarial multi-tenant',
        theme_color: '#1976d2',
        background_color: '#ffffff',
        display: 'standalone',
        scope: '/',
        start_url: '/',
        icons: [
          { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        runtimeCaching: [
          {
            urlPattern: /^\/api\//,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 50, maxAgeSeconds: 300 },
              networkTimeoutSeconds: 5,
            },
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    // Los specs de Playwright viven en `e2e/` y NO los corre Vitest (requieren
    // navegador + servidor vivos). Se excluyen para que el job unit no los tome.
    exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      // El contrato generado (schema.d.ts) y el esquema versionado no son código
      // ejecutable: se excluyen del denominador de cobertura.
      exclude: ['node_modules/', 'src/test-setup.ts', 'src/api/**', 'e2e/**'],
      // INFRA-NEW-3: el gate de cobertura ahora SÍ corre en CI (npm run
      // test:coverage). Los umbrales son un "ratchet" fijado al piso actual del
      // código para prevenir regresión; el objetivo del Plan Maestro es 60% en
      // las cuatro métricas y se sube conforme se agregan tests. No bajar.
      thresholds: {
        statements: 52,
        branches: 41,
        functions: 45,
        lines: 55,
        // TEST-6: pisos de cobertura por carpeta (ratchet, igual filosofía que el
        // global). Fijados al piso ACTUAL de cada carpeta para impedir regresión.
        // El objetivo del Plan Maestro (≥85% en services/ y hooks/) sigue pendiente:
        // el gap es grande (hooks ~50%, services ~63%) y no se cierra con 1-2 tests;
        // se sube conforme se agregan tests con MSW. NO bajar estos números.
        'src/services/**': {
          statements: 60,
          branches: 50,
          functions: 55,
          lines: 60,
        },
        'src/hooks/**': {
          statements: 45,
          branches: 33,
          functions: 50,
          lines: 45,
        },
        'src/lib/**': {
          statements: 85,
          branches: 70,
          functions: 85,
          lines: 85,
        },
      },
    },
  },
})
