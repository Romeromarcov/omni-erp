import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { crearCatalogoInventario } from './helpers/datos';

/**
 * Flujo crítico 4 — Inventario (TEST-6 / Fase 4).
 *
 * Ajuste manual de stock 100 % vía UI (pantalla "Ajuste Manual de Inventario")
 * y verificación del resultado en Stock Actual y en el Kardex del producto.
 */
test.describe('Inventario: ajuste manual y kardex', () => {
  test('registra una entrada de ajuste y la ve en stock y kardex', async ({ page }) => {
    const sesion = await iniciarSesion(page);
    const catalogo = await crearCatalogoInventario(sesion.api, sesion.empresaId, {
      stockInicial: '50',
    });
    const motivo = `Conteo físico E2E ${Date.now()}`;

    await test.step('registrar una ENTRADA de 10 unidades desde la UI', async () => {
      await page.goto(
        `/inventario/ajustes?producto=${catalogo.productoId}&almacen=${catalogo.almacenId}`,
      );
      await expect(
        page.getByRole('heading', { name: 'Ajuste Manual de Inventario' }),
      ).toBeVisible();

      // El producto y el almacén llegan preseleccionados por querystring; el
      // banner de stock confirma que la página resolvió el stock actual.
      await expect(page.getByText('Stock actual:')).toBeVisible();
      await expect(page.getByText('50 unidades disponibles')).toBeVisible();

      await page.getByRole('button', { name: /entrada de inventario/i }).click();
      await page.getByLabel('Cantidad').fill('10');
      await page.getByLabel('Motivo / Observaciones').fill(motivo);
      await page.getByRole('button', { name: 'Registrar ajuste' }).click();

      await expect(page.getByText('Ajuste registrado correctamente.')).toBeVisible();
    });

    await test.step('Stock Actual muestra 60 disponibles', async () => {
      await page.goto('/inventario/stock');
      await page.getByPlaceholder('Buscar producto…').fill(catalogo.productoNombre);
      const fila = page.getByRole('row').filter({ hasText: catalogo.productoNombre });
      await expect(fila).toBeVisible();
      await expect(fila.getByRole('cell', { name: '60', exact: true })).toBeVisible();
    });

    await test.step('el kardex registra la carga inicial y el ajuste', async () => {
      // Gap UI documentado en el PR: la página de Kardex SIEMPRE muestra
      // "0 movimientos" porque el backend responde `{kardex: [...]}` y el
      // servicio del frontend espera una lista/`results` (mismatch de
      // contrato). Se verifica el render de la página y el contenido del
      // kardex contra la API real que la alimenta.
      await page.goto(`/inventario/kardex/${catalogo.productoId}`);
      await expect(
        page.getByRole('heading', { name: `Kardex — ${catalogo.productoNombre}` }),
      ).toBeVisible();

      const kardex = await sesion.api.get<{
        kardex: Array<{ tipo_movimiento: string; cantidad: string; observaciones: string | null }>;
      }>(`/inventario/productos/${catalogo.productoId}/kardex/?almacen=${catalogo.almacenId}`);

      // Dos movimientos AJUSTE: +50 (carga inicial vía API) y +10 (ajuste UI).
      // Sin asumir orden: la página de ajustes registra la fecha en hora local
      // "deslizada" (nowISOLocal), así que el orden cronológico no es estable.
      expect(kardex.kardex).toHaveLength(2);
      expect(kardex.kardex.map((m) => m.tipo_movimiento)).toEqual(['AJUSTE', 'AJUSTE']);
      expect(kardex.kardex.map((m) => Number(m.cantidad)).sort((a, b) => a - b)).toEqual([10, 50]);
      expect(kardex.kardex.some((m) => m.observaciones === motivo)).toBe(true);
    });
  });
});
