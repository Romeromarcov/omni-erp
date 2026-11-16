import { test as setup, expect } from '@playwright/test';
import {
  credencialesE2E,
  AUTH_STORAGE_FILE,
  guardarAccessCache,
} from './helpers/sesion';

/**
 * Setup de autenticación (solución estructural de la suite E2E).
 *
 * Hace UN solo login y persiste el estado del navegador (la cookie httpOnly
 * `refresh_token`) en `AUTH_STORAGE_FILE` más el `access` token inicial (15 min)
 * en caché local para el cliente API de seeding. Así la suite hace 1 login en vez
 * de ~37, evitando los rate-limits de login (5/min, SEC-07) y refresh (20/min,
 * M-SEC-13).
 */
setup('autenticación: login único → storageState', async ({ page }) => {
  const { usuario, password } = credencialesE2E();

  let resp = await page.request.post('/api/auth/login/', {
    data: { username: usuario, password },
  });
  // Tolera la ventana del throttle de login (5/min por IP) una vez.
  if (resp.status() === 429) {
    await page.waitForTimeout(61_000);
    resp = await page.request.post('/api/auth/login/', {
      data: { username: usuario, password },
    });
  }
  expect(resp.ok(), `login setup → ${resp.status()}: ${await resp.text()}`).toBeTruthy();
  const cuerpo = (await resp.json()) as { access?: string };
  if (cuerpo.access) {
    guardarAccessCache(cuerpo.access);
  }

  // El refresh_token httpOnly quedó en el contexto del navegador; lo persistimos.
  await page.context().storageState({ path: AUTH_STORAGE_FILE });
});

