import { test as setup, expect } from '@playwright/test';
import { credencialesE2E, AUTH_STORAGE_FILE } from './helpers/sesion';

/**
 * Setup de autenticación (solución estructural de la suite E2E).
 *
 * Hace UN solo login y persiste el estado del navegador (la cookie httpOnly
 * `refresh_token`) en `AUTH_STORAGE_FILE`. Todos los specs reusan ese
 * `storageState` y obtienen su `access` fresco vía `/api/auth/token/refresh/`
 * (que NO está sujeto al throttle de login de 5/min, SEC-07). Así la suite hace
 * 1 login en vez de ~37, evitando el rate-limit que volvía la suite frágil, y
 * permite correrla localmente (la cookie se inyecta, no depende del bootstrap).
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

  // El refresh_token httpOnly quedó en el contexto del navegador; lo persistimos.
  await page.context().storageState({ path: AUTH_STORAGE_FILE });
});
