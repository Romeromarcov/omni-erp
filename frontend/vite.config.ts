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
      // código para prevenir regresión; el objetivo de la Fase 4 del plan
      // cero-dudas es 80% y se sube por escalones conforme se agregan tests.
      // No bajar. Piso actual (Q1/COV-2 escalón 3, OBJETIVO 80% ALCANZADO):
      // stmts 80.7 / branches 70.9 / funcs 71.0 / lines 82.7 — umbral con ~2 puntos de margen.
      thresholds: {
        statements: 79,
        branches: 69,
        functions: 69,
        lines: 81,
        // TEST-6: pisos de cobertura por carpeta (ratchet, igual filosofía que el
        // global). Fijados al piso ACTUAL de cada carpeta para impedir regresión.
        // El objetivo del Plan Maestro (≥85% en services/ y hooks/) sigue pendiente;
        // se sube conforme se agregan tests con MSW. NO bajar estos números.
        // Piso actual: services 93.1/86.5/90/94.9 · hooks 88.3/78.7/84.4/91.2
        // (escalón 3: services/api a fondo + useFacturaFiscalForm con suite propia).
        'src/services/**': {
          statements: 91,
          branches: 84,
          functions: 88,
          lines: 93,
        },
        'src/hooks/**': {
          statements: 86,
          branches: 77,
          functions: 82,
          lines: 89,
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
