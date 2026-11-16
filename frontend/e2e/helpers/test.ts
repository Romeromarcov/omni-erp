import fs from 'node:fs';
import { test as base } from '@playwright/test';

export * from '@playwright/test';

const VENTANA_REFRESH_MS = 61_000;
/** Deja holgura bajo M-SEC-13 (20 POST/min a `/auth/token/refresh/`) para specs con varias cargas. */
const MAX_REFRESHES_POR_VENTANA = 15;
const marcasRefresh: number[] = [];

/**
 * `test` de Playwright para los E2E:
 *   1) Cada carga de documento arranca con la caché de datos persistida de la app
 *      (`omni-erp-cache` en IndexedDB) VACÍA para probar siempre contra el backend real.
 *   2) Respeta la ventana de `M-SEC-13` (20 refreshes/min) antes de iniciar un spec si los
 *      anteriores ya consumieron el presupuesto del minuto.
 *   3) Al cerrar el spec, persiste la cookie `refresh_token` rotada por el backend
 *      (`ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION`, M-SEC-4) en `e2e/.auth/admin.json`
 *      —solo cookies, sin `origins`/`localStorage` para no contaminar specs como
 *      `login-multiempresa`—, evitando que el siguiente spec use un refresh ya invalidado.
 */
export const test = base.extend({
  // El segundo parámetro se llama `entregar` y no `use` (nombre de Playwright) para que la regla
  // react-hooks/rules-of-hooks no lo confunda con un hook de React.
  context: async ({ context }, entregar) => {
    const ahora = Date.now();
    while (marcasRefresh.length > 0 && ahora - marcasRefresh[0] >= VENTANA_REFRESH_MS) {
      marcasRefresh.shift();
    }
    if (marcasRefresh.length >= MAX_REFRESHES_POR_VENTANA) {
      const espera = VENTANA_REFRESH_MS - (ahora - marcasRefresh[0]);
      if (espera > 0) {
        await new Promise((r) => setTimeout(r, espera));
      }
    }

    context.on('request', (req) => {
      if (req.method() === 'POST' && req.url().includes('/api/auth/token/refresh/')) {
        marcasRefresh.push(Date.now());
      }
    });

    await context.addInitScript(() => {
      try {
        indexedDB.deleteDatabase('omni-erp-cache');
      } catch {
        // Sin IndexedDB no hay caché persistido que vaciar.
      }
    });

    await entregar(context);

    try {
      const cookies = await context.cookies();
      if (cookies.some((c) => c.name === 'refresh_token' && c.value)) {
        await fs.promises.writeFile(
          'e2e/.auth/admin.json',
          JSON.stringify({ cookies, origins: [] }, null, 2),
        );
      }
    } catch {
      // Si el contexto ya fue cerrado manualmente por el spec, conservar el último estado válido.
    }
  },
});

