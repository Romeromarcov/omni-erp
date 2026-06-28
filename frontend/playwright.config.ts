import { defineConfig, devices } from '@playwright/test';

/**
 * Configuración de Playwright (TEST-6 — E2E de flujos críticos).
 *
 * Requiere backend + frontend vivos (NO corre en el job unit de CI). La baseURL
 * sale de `E2E_BASE_URL`; por defecto apunta al dev server de Vite (5173).
 *
 * Uso local (detalle completo en `e2e/README.md`):
 *   1) backend en :8000 + seed (`manage.py seed_empresa_inicial` ×2)
 *   2) npm run dev            (frontend en :5173, proxy /api → :8000)
 *   3) npx playwright install  (una vez, descarga los navegadores)
 *   4) E2E_ADMIN_PASSWORD=… npm run test:e2e
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5173';

export default defineConfig({
  testDir: './e2e',
  // Los flujos comparten una sola BD del backend y el login tiene rate-limit
  // (SEC-07: 5/min por IP): se corren en serie para que los specs no se pisen
  // los datos ni agoten la ventana de logins.
  fullyParallel: false,
  workers: 1,
  // Los flujos hacen seeding vía API + varias verificaciones de UI por test.
  timeout: 120_000,
  expect: { timeout: 10_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  projects: [
    // Login único: persiste el storageState (cookie refresh) que reusa el resto.
    { name: 'setup', testMatch: /global\.setup\.ts/ },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Todos los specs arrancan autenticados con la cookie del login único.
        storageState: 'e2e/.auth/admin.json',
      },
      dependencies: ['setup'],
    },
  ],
});
