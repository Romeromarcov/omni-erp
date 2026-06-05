import { defineConfig, devices } from '@playwright/test';

/**
 * Configuración de Playwright (TEST-6 — E2E smoke).
 *
 * Requiere backend + frontend vivos (NO corre en el job unit de CI). La baseURL
 * sale de `E2E_BASE_URL`; por defecto apunta al dev server de Vite (5173).
 *
 * Uso local:
 *   1) npm run dev            (frontend en :5173, con backend en :8000)
 *   2) npx playwright install  (una vez, descarga los navegadores)
 *   3) npm run test:e2e
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5173';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
