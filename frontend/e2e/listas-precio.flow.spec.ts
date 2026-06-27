import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Listas de Precio (ventas) — frontend e2e.
 *
 * Crea una lista de precios 100 % vía UI, la verifica en la lista, abre el drawer
 * de precios y agrega un precio para un producto. El backend de ventas
 * (/api/ventas/listas-precio/, /api/ventas/detalles-precio/) ya está operativo;
 * la sesión y la empresa primaria las resuelve `iniciarSesion`.
 */
test.describe('Ventas: listas de precio', () => {
  test('crea una lista, agrega un precio y lo ve', async ({ page }) => {
    await iniciarSesion(page);

    const suf = sufijoUnico();
    const nombre = `Lista E2E ${suf}`;
    const codigo = `LE2E${suf}`.slice(0, 20);

    await test.step('navegar a Listas de Precio', async () => {
      await page.goto('/ventas/listas-precio');
      await expect(page.getByRole('heading', { name: 'Listas de Precio' })).toBeVisible();
    });

    await test.step('crear una lista nueva', async () => {
      await page.getByRole('button', { name: 'Nueva lista' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva lista de precios' })).toBeVisible();

      await page.getByLabel(/Nombre/).fill(nombre);
      await page.getByLabel(/Código/).fill(codigo);
      // Selecciona la primera moneda disponible del seed.
      await page.getByLabel(/Moneda/).click();
      await page.getByRole('option').first().click();
      await page.getByRole('button', { name: 'Guardar' }).click();

      await expect(page.getByRole('heading', { name: 'Nueva lista de precios' })).toBeHidden();
    });

    await test.step('la lista aparece y se abre el drawer de precios', async () => {
      await page.getByLabel('Buscar').fill(nombre);
      const fila = page.getByRole('row').filter({ hasText: nombre });
      await expect(fila).toBeVisible();
      await fila.getByRole('button', { name: 'Precios' }).click();
      await expect(page.getByText('Precios por producto')).toBeVisible();
    });

    await test.step('agregar un precio para un producto', async () => {
      // Selecciona el primer producto disponible del seed de inventario.
      await page.getByLabel(/Producto/).click();
      await page.getByRole('option').first().click();
      await page.getByLabel('Precio', { exact: true }).fill('25.00');
      await page.getByRole('button', { name: 'Agregar precio' }).click();

      // El precio aparece listado en el drawer (25.0000 tras normalizar el Decimal).
      await expect(page.getByText(/25\.0000/)).toBeVisible();
    });
  });
});
