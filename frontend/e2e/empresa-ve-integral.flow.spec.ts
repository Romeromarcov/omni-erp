import { test, expect } from './helpers/test';
import { iniciarSesion } from './helpers/sesion';

/**
 * Auditoría E2E integral del navegador — Recorrido multi-módulo Empresa VE.
 *
 * Verifica sobre el bundle compilado (`vite preview`) y backend real que todas
 * las vistas operativas críticas y portales independientes renderizan sin
 * errores JavaScript no capturados (`pageerror`), sin respuestas HTTP >= 500
 * ni pantallas en blanco.
 */
test.describe('Auditoría E2E Navegador: Cobertura Integral Multi-Módulo VE', () => {
  test('recorre módulos operativos y portales sin pageerror ni errores 5xx', async ({ page }) => {
    const erroresJs: string[] = [];
    const erroresApi5xx: string[] = [];

    page.on('pageerror', (err) => {
      erroresJs.push(`${page.url()} -> ${err.message}`);
    });
    page.on('response', (resp) => {
      if (resp.url().includes('/api/') && resp.status() >= 500) {
        erroresApi5xx.push(`${resp.status()} ${resp.url()}`);
      }
    });

    await iniciarSesion(page);

    const rutasAutenticadas: string[] = [
      '/inicio',
      '/ventas/pedidos',
      '/ventas/notas-venta',
      '/ventas/facturas-fiscales',
      '/ventas/listas-precio',
      '/ventas/portal-vendedor',
      '/compras/ordenes',
      '/compras/cuentas-por-pagar',
      '/inventario/productos',
      '/inventario/stock',
      '/contabilidad/reportes',
      '/fiscal/libro-ventas',
      '/fiscal/libro-compras',
      '/nomina/procesos',
      '/tesoreria/cambio-divisa',
      '/tesoreria/conciliaciones',
      '/gastos',
      '/crm/pipeline',
      '/despacho',
      '/despacho/portal-conductor',
      '/agentes',
    ];

    // Iniciar dentro del origin SPA con page.goto('/inicio') y recorrer el resto
    // con history.pushState + popstate para conservar el access token sin recargar 21 veces.
    for (const [idx, ruta] of rutasAutenticadas.entries()) {
      await test.step(`navegar a ${ruta}`, async () => {
        if (idx === 0) {
          await page.goto(ruta, { waitUntil: 'domcontentloaded' });
        } else {
          await page.evaluate((path) => {
            window.history.pushState({}, '', path);
            window.dispatchEvent(new PopStateEvent('popstate'));
          }, ruta);
        }
        await expect.poll(() => new URL(page.url()).pathname, { timeout: 10_000 }).toBe(ruta);
        await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});
        const texto = await page.locator('body').innerText();
        expect(texto.trim().length, `Pantalla vacía en ${ruta}`).toBeGreaterThan(20);
        expect(page.url()).not.toContain('/login');
      });
    }

    await test.step('verificar ruta pública /portal/cliente sin errores 5xx o pageerror', async () => {
      await page.goto('/portal/cliente', { waitUntil: 'domcontentloaded' });
      await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});
      const texto = await page.locator('body').innerText();
      expect(texto.trim().length, 'Pantalla vacía en /portal/cliente').toBeGreaterThan(15);
    });

    expect(erroresJs, `Errores JS detectados:\n${erroresJs.join('\n')}`).toEqual([]);
    expect(erroresApi5xx, `Respuestas API >= 500:\n${erroresApi5xx.join('\n')}`).toEqual([]);
  });
});
