import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// BACKEND_URL puede venir del entorno:
//   - Local dev:  no se setea → default localhost:8000
//   - Docker dev: se setea como http://backend:8000 en docker-compose.yml
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const backendUrl: string = (globalThis as any).process?.env?.BACKEND_URL ?? 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
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
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: ['node_modules/', 'src/test-setup.ts'],
      // INFRA-NEW-3: el gate de cobertura ahora SÍ corre en CI (npm run
      // test:coverage). Los umbrales son un "ratchet" fijado al piso actual del
      // código para prevenir regresión; el objetivo del Plan Maestro es 60% en
      // las cuatro métricas y se sube conforme se agregan tests. No bajar.
      thresholds: {
        statements: 52,
        branches: 41,
        functions: 45,
        lines: 55,
      },
    },
  },
})
