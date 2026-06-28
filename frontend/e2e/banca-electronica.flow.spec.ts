import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Banca Electrónica — Cuentas bancarias de la empresa (frontend e2e).
 *
 * Crea una cuenta bancaria 100 % vía UI desde la página de Banca Electrónica y
 * la verifica en la lista. El backend ya está operativo
 * (prefijo /api/banca-electronica/); la sesión y la empresa primaria las
 * resuelve `iniciarSesion`.
 */
test.describe('Banca Electrónica: cuentas bancarias de la empresa', () => {
  test('crea una cuenta desde la UI y la ve en la lista', async ({ page }) => {
    await iniciarSesion(page);

    const suf = sufijoUnico();
    const banco = `Banco E2E ${suf}`;
    // Número de cuenta único (es unique en el backend).
    const numeroCuenta = `0102-${String(Date.now()).slice(-10)}`;

    await test.step('navegar a la página de Banca Electrónica', async () => {
      await page.goto('/banca-electronica');
      await expect(page.getByRole('heading', { name: 'Banca Electrónica' })).toBeVisible();
    });

    await test.step('crear una cuenta bancaria nueva', async () => {
      await page.getByRole('button', { name: 'Nueva cuenta' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva cuenta' })).toBeVisible();

      await page.getByLabel(/Banco/).fill(banco);
      await page.getByLabel(/Número de cuenta/).fill(numeroCuenta);

      // Selecciona la primera moneda disponible del select.
      await page.getByLabel(/Moneda/).click();
      await page.getByRole('option').first().click();

      await page.getByRole('button', { name: 'Guardar' }).click();

      // El diálogo se cierra al guardar correctamente.
      await expect(page.getByRole('heading', { name: 'Nueva cuenta' })).toBeHidden();
    });

    await test.step('la cuenta aparece en la lista', async () => {
      const fila = page.getByRole('row').filter({ hasText: banco });
      await expect(fila).toBeVisible();
      await expect(fila.getByText(numeroCuenta)).toBeVisible();
    });
  });
});
