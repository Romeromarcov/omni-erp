import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';

/**
 * Flujo Comisiones de Ventas — frontend e2e.
 *
 * Crea un esquema de comisión 100 % vía UI desde /ventas/comisiones, lo verifica
 * en la lista de esquemas y revisa la pestaña de comisiones devengadas. El backend
 * de ventas (/api/ventas/esquemas-comision/, /api/ventas/comisiones/) ya está
 * operativo; la sesión y la empresa primaria las resuelve `iniciarSesion`.
 */
test.describe('Ventas: comisiones', () => {
  test('crea un esquema, lo ve y revisa las comisiones devengadas', async ({ page }) => {
    await iniciarSesion(page);

    await test.step('navegar a Comisiones', async () => {
      await page.goto('/ventas/comisiones');
      await expect(page.getByRole('heading', { name: 'Comisiones de Ventas' })).toBeVisible();
    });

    await test.step('crear un esquema de comisión', async () => {
      await page.getByRole('button', { name: 'Nuevo esquema' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo esquema' })).toBeVisible();

      // Selecciona el primer vendedor disponible del seed de usuarios.
      await page.getByLabel(/Vendedor/).click();
      await page.getByRole('option').first().click();
      await page.getByLabel(/Porcentaje base/).fill('5');
      await page.getByRole('button', { name: 'Guardar' }).click();

      await expect(page.getByRole('heading', { name: 'Nuevo esquema' })).toBeHidden();
    });

    await test.step('el esquema aparece en la lista', async () => {
      await expect(page.getByText('5.0000%')).toBeVisible();
    });

    await test.step('revisar la pestaña de comisiones devengadas', async () => {
      await page.getByRole('tab', { name: 'Comisiones devengadas' }).click();
      await expect(page.getByRole('button', { name: 'Liquidar' })).toBeVisible();
    });
  });
});
