import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Costos — Costeo de producción (frontend e2e).
 *
 * Crea un costo estándar 100 % vía UI desde la página de Costos (tab "Costo
 * estándar") y lo verifica en la lista. El backend de costos ya está operativo
 * (prefijo /api/costos/); la sesión y la empresa primaria las resuelve
 * `iniciarSesion`. Se apoya en que exista al menos un producto y una moneda
 * sembrados por `seed_empresa_inicial`.
 */
test.describe('Costos: costeo de producción', () => {
  test('crea un costo estándar desde la UI y lo ve en la lista', async ({ page }) => {
    await iniciarSesion(page);

    const suf = sufijoUnico();
    const costoUnitario = `${100 + Number(suf.slice(-3))}.00`;

    await test.step('navegar a la página de Costos', async () => {
      await page.goto('/costos');
      await expect(page.getByRole('heading', { name: 'Costos' })).toBeVisible();
    });

    await test.step('ir al tab de Costo estándar', async () => {
      await page.getByRole('tab', { name: 'Costo estándar' }).click();
      await expect(page.getByRole('button', { name: 'Nuevo costo estándar' })).toBeVisible();
    });

    await test.step('crear un costo estándar nuevo', async () => {
      await page.getByRole('button', { name: 'Nuevo costo estándar' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo costo estándar' })).toBeVisible();

      const dialog = page.getByRole('dialog');

      // Producto: seleccionar la primera opción real del combo.
      await dialog.getByLabel(/Producto/).click();
      const opciones = page.getByRole('option').filter({ hasNotText: 'Seleccione' });
      await opciones.first().click();

      await dialog.getByLabel(/Costo unitario estándar/).fill(costoUnitario);
      await dialog.getByLabel(/Vigencia desde/).fill('2026-07-01');

      await dialog.getByRole('button', { name: 'Guardar' }).click();
      // El diálogo se cierra al guardar correctamente.
      await expect(page.getByRole('heading', { name: 'Nuevo costo estándar' })).toBeHidden();
    });

    await test.step('el costo estándar aparece en la lista', async () => {
      await expect(page.getByText(costoUnitario).first()).toBeVisible();
    });
  });
});
